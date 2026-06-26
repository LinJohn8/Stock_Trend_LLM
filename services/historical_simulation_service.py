from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select

from data_sources.index_client import IndexClient
from database.db import session_scope
from database.models import HistoricalSimulation
from services.ai_analysis_service import AIAnalysisService
from services.algorithm_service import AlgorithmService
from services.fundamental_service import FundamentalService
from services.news_ingestion_service import NewsIngestionService
from services.risk_service import RiskService
from services.sentiment_service import SentimentService
from services.stock_data_service import StockDataService
from utils.math_utils import clamp
from utils.stock_utils import normalize_stock_code


@dataclass(frozen=True)
class SimulationConfig:
    stock_code: str
    stock_name: str = ""
    start_date: date | None = None
    end_date: date | None = None
    initial_cash: float = 100000
    selected_algorithm_ids: list[str] | None = None
    strategy_mode: str = "consensus"
    benchmark_code: str = "sh000300"
    fee_rate: float = 0.0003
    max_position: float = 0.85


class HistoricalSimulationService:
    """Replay deterministic algorithms over historical bars and compare with a benchmark."""

    def __init__(self) -> None:
        self.algorithm_service = AlgorithmService()

    def run(self, config: SimulationConfig) -> dict[str, Any]:
        code = normalize_stock_code(config.stock_code)
        end_date = config.end_date or date.today()
        start_date = config.start_date or (end_date - timedelta(days=180))
        data = self._load_stock_data(code, start_date, end_date)
        if len(data) < 40:
            raise ValueError("历史行情不足，至少需要约 40 个交易日才能模拟。")

        selected_ids = config.selected_algorithm_ids or self.algorithm_service.default_algorithm_ids()
        algorithms = [algo for algo in self.algorithm_service.list_algorithms() if algo.id in set(selected_ids)]
        diagnostics: dict[str, Any] = {
            "data": {
                "stock_code": code,
                "rows": len(data),
                "first_date": data.iloc[0]["date"] if not data.empty else None,
                "last_date": data.iloc[-1]["date"] if not data.empty else None,
                "status": "ok",
            },
            "algorithms": {},
            "trade_blockers": [],
        }
        fundamental = FundamentalService().analyze(code)
        sentiment = SentimentService().analyze(code)
        news_evidence = NewsIngestionService().get_evidence(code, limit=12)
        memories = self.algorithm_service._memories(code)

        cash = float(config.initial_cash)
        shares = 0
        trades: list[dict[str, Any]] = []
        curve: list[dict[str, Any]] = []
        prior_equity = cash

        for index in range(20, len(data)):
            window = data.iloc[: index + 1].copy()
            current = window.iloc[-1]
            technical = self._technical_snapshot(code, window)
            risk = RiskService().evaluate(config.stock_name, technical, sentiment)
            ctx = {
                "stock_code": code,
                "stock_name": config.stock_name,
                "technical": technical,
                "fundamental": fundamental,
                "sentiment": sentiment,
                "news_evidence": news_evidence,
                "risk": risk,
                "daily": window,
                "holding": self._paper_holding(shares, cash, current["close"], config.initial_cash),
                "memories": memories,
            }
            results = []
            for algo in algorithms:
                try:
                    raw = algo.runner(ctx)
                    normalized = self.algorithm_service._normalize_result(raw, algo)
                    results.append(normalized)
                    self._record_algorithm_diagnostic(diagnostics, algo, normalized, current["date"])
                except Exception as exc:
                    diagnostics["algorithms"].setdefault(
                        algo.id,
                        {"name": algo.name, "category": algo.category, "status": "error", "warnings": 0, "errors": 0, "examples": []},
                    )
                    diagnostics["algorithms"][algo.id]["errors"] += 1
                    diagnostics["algorithms"][algo.id]["examples"].append(
                        {"date": current["date"], "step": "algorithm_runner", "message": str(exc)}
                    )
                    results.append(
                        self.algorithm_service._normalize_result(
                            {
                                "score": 50,
                                "view": algo.category,
                                "direction": "neutral",
                                "position_bias": 0,
                                "reasons": [f"算法执行失败，已按中性处理：{exc}"],
                                "risks": ["该算法在本次模拟中出现异常，需要检查数据或参数。"],
                            },
                            algo,
                        )
                    )
            decision = self.algorithm_service.combine_results(results, ctx)
            target_fraction = self._target_fraction(decision, config.strategy_mode, config.max_position)
            price = float(current["close"])
            equity = cash + shares * price
            target_value = equity * target_fraction
            current_value = shares * price
            trade_value = target_value - current_value

            if abs(trade_value) > max(1000, equity * 0.02):
                if trade_value > 0:
                    buy_value = min(cash, trade_value)
                    quantity = int(buy_value // (price * 100)) * 100
                    if quantity > 0:
                        cost = quantity * price
                        fee = cost * config.fee_rate
                        cash -= cost + fee
                        shares += quantity
                        trades.append(self._trade_row(current["date"], "buy", quantity, price, fee, decision))
                    elif target_fraction > 0:
                        required_cash = price * 100 * (1 + config.fee_rate)
                        self._record_trade_blocker(
                            diagnostics,
                            current["date"],
                            "cash_below_one_lot",
                            f"目标买入但现金 {cash:.2f} 不足以买入一手，最低约需 {required_cash:.2f}。",
                        )
                else:
                    quantity = min(shares, int(abs(trade_value) // (price * 100)) * 100)
                    if quantity > 0:
                        revenue = quantity * price
                        fee = revenue * config.fee_rate
                        cash += revenue - fee
                        shares -= quantity
                        trades.append(self._trade_row(current["date"], "sell", quantity, price, fee, decision))
            elif target_fraction > 0 and shares <= 0:
                required_cash = price * 100 * (1 + config.fee_rate)
                if cash < required_cash:
                    self._record_trade_blocker(
                        diagnostics,
                        current["date"],
                        "cash_below_one_lot",
                        f"资金 {cash:.2f} 低于一手成本 {required_cash:.2f}，仅展示走势，不执行买入。",
                    )

            equity = cash + shares * price
            daily_return = 0 if prior_equity <= 0 else equity / prior_equity - 1
            prior_equity = equity
            curve.append(
                {
                    "date": current["date"],
                    "close": price,
                    "cash": cash,
                    "shares": shares,
                    "equity": equity,
                    "position": 0 if equity <= 0 else shares * price / equity,
                    "daily_return": daily_return,
                    "action": decision["action"],
                    "score": decision["overall_score"],
                    "confidence": decision["confidence"],
                    "benchmark_return": None,
                    "trade_signal": "hold" if shares else "watch",
                }
            )

        benchmark = self._benchmark_curve(config.benchmark_code, start_date, end_date, curve)
        for row, bench_ret in zip(curve, benchmark):
            row["benchmark_return"] = bench_ret

        summary = self._summary(curve, trades, config.initial_cash, benchmark)
        diagnostics["summary"] = self._diagnostic_summary(diagnostics)
        output = {
            "stock_code": code,
            "stock_name": config.stock_name,
            "start_date": start_date,
            "end_date": end_date,
            "initial_cash": config.initial_cash,
            "strategy_mode": config.strategy_mode,
            "selected_algorithms": [algo.id for algo in algorithms],
            "benchmark_code": config.benchmark_code,
            "fee_rate": config.fee_rate,
            "max_position": config.max_position,
            "summary": summary,
            "equity_curve": curve,
            "trades": trades,
            "diagnostics": diagnostics,
            "ai_review": AIAnalysisService().review_simulation(
                {
                    "stock_code": code,
                    "stock_name": config.stock_name,
                    "summary": summary,
                    "diagnostics": diagnostics,
                    "trades": trades[:20],
                    "selected_algorithms": [algo.id for algo in algorithms],
                }
            ),
        }
        self.save(output)
        return output

    def save(self, output: dict[str, Any]) -> HistoricalSimulation:
        summary = output["summary"]
        with session_scope() as session:
            item = HistoricalSimulation(
                stock_code=output["stock_code"],
                stock_name=output.get("stock_name", ""),
                start_date=output["start_date"],
                end_date=output["end_date"],
                initial_cash=output["initial_cash"],
                strategy_mode=output["strategy_mode"],
                selected_algorithms=json.dumps(output["selected_algorithms"], ensure_ascii=False),
                benchmark_code=output["benchmark_code"],
                fee_rate=output.get("fee_rate", 0.0003),
                max_position=output.get("max_position", 0.85),
                summary_json=json.dumps(summary, ensure_ascii=False, default=str),
                equity_curve_json=json.dumps(output["equity_curve"], ensure_ascii=False, default=str),
                trades_json=json.dumps(output["trades"], ensure_ascii=False, default=str),
                diagnostics_json=json.dumps(output.get("diagnostics", {}), ensure_ascii=False, default=str),
                ai_review=output.get("ai_review", ""),
                final_return=summary["final_return"],
                benchmark_return=summary.get("benchmark_return"),
                max_drawdown=summary["max_drawdown"],
                win_rate=summary["win_rate"],
            )
            session.add(item)
            session.flush()
            session.refresh(item)
            return item

    def list_runs(self, stock_code: str | None = None, limit: int = 50) -> list[HistoricalSimulation]:
        with session_scope() as session:
            stmt = select(HistoricalSimulation).order_by(HistoricalSimulation.created_at.desc()).limit(limit)
            if stock_code:
                stmt = stmt.where(HistoricalSimulation.stock_code == normalize_stock_code(stock_code))
            return list(session.scalars(stmt).all())

    def _load_stock_data(self, stock_code: str, start_date: date, end_date: date) -> pd.DataFrame:
        service = StockDataService()
        service.update_daily_data(stock_code, days=max(420, (end_date - start_date).days + 120))
        df = service.get_daily_dataframe(stock_code, limit=1200)
        if df.empty:
            return df
        mask = (df["date"] >= start_date) & (df["date"] <= end_date)
        return df.loc[mask].sort_values("date").reset_index(drop=True)

    def _technical_snapshot(self, stock_code: str, df: pd.DataFrame) -> dict[str, Any]:
        close = df["close"].astype(float)
        latest = df.iloc[-1]
        ma5 = close.rolling(5).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else None
        ret5 = _period_return(close, 5)
        ret20 = _period_return(close, 20)
        ret60 = _period_return(close, 60)
        volume = df["volume"].astype(float)
        volume_ratio = volume.iloc[-1] / volume.rolling(20).mean().iloc[-1] if len(volume) >= 20 and volume.rolling(20).mean().iloc[-1] else None
        max_drawdown = _max_drawdown(close.tail(60))
        trend_score = 50
        if ma20 and latest["close"] > ma20:
            trend_score += 15
        if ma60 and latest["close"] > ma60:
            trend_score += 15
        if ret20 < -0.08:
            trend_score -= 15
        momentum_score = 50 + ret20 * 120 + ret60 * 60
        return {
            "stock_code": stock_code,
            "date": latest["date"],
            "current_price": float(latest["close"]),
            "ma5": _to_float(ma5),
            "ma20": _to_float(ma20),
            "ma60": _to_float(ma60),
            "rsi": None,
            "macd": None,
            "volume_ratio": _to_float(volume_ratio),
            "ret5": ret5,
            "ret20": ret20,
            "ret60": ret60,
            "max_drawdown": max_drawdown,
            "trend_score": clamp(trend_score),
            "momentum_score": clamp(momentum_score),
            "risk_score": clamp(70 - (20 if max_drawdown < -0.15 else 0)),
            "technical_summary": f"回放日 {latest['date']} 收盘 {latest['close']:.2f}，近20日收益 {ret20:.2%}。",
        }

    def _paper_holding(self, shares: int, cash: float, price: float, initial_cash: float) -> dict[str, Any] | None:
        if shares <= 0:
            return None
        equity = cash + shares * price
        return {
            "current_quantity": shares,
            "profit_rate": equity / initial_cash - 1,
            "status": "paper_holding",
        }

    def _target_fraction(self, decision: dict[str, Any], strategy_mode: str, max_position: float) -> float:
        score = decision["overall_score"]
        action = decision["action"]
        if strategy_mode == "conservative":
            if action == "buy_candidate" and score >= 72:
                return min(max_position, 0.45)
            if action in {"watch", "hold"} and score >= 60:
                return min(max_position, 0.25)
            return 0
        if strategy_mode == "aggressive":
            if action == "buy_candidate":
                return min(max_position, 0.75)
            if action in {"watch", "hold"}:
                return min(max_position, 0.45)
            return 0.15 if action == "uncertain" and score >= 52 else 0
        if action == "buy_candidate":
            return min(max_position, 0.60)
        if action in {"watch", "hold"}:
            return min(max_position, 0.35)
        return 0

    def _benchmark_curve(self, benchmark_code: str, start_date: date, end_date: date, curve: list[dict[str, Any]]) -> list[float | None]:
        df = self._load_benchmark(benchmark_code)
        if df.empty or not curve:
            return [None for _ in curve]
        df = df[(df["date"] >= start_date) & (df["date"] <= end_date)].sort_values("date")
        if df.empty:
            return [None for _ in curve]
        base = float(df.iloc[0]["close"])
        values = []
        for row in curve:
            matched = df[df["date"] <= row["date"]]
            values.append(None if matched.empty or base <= 0 else float(matched.iloc[-1]["close"]) / base - 1)
        return values

    def _load_benchmark(self, benchmark_code: str) -> pd.DataFrame:
        client = IndexClient()
        if benchmark_code == "sh000001":
            return client.get_shanghai_daily()
        if benchmark_code == "sz399001":
            return client.get_shenzhen_daily()
        if benchmark_code == "sz399006":
            return client.get_chinext_daily()
        return client.get_hs300_daily()

    def _trade_row(self, trade_date, side: str, quantity: int, price: float, fee: float, decision: dict[str, Any]) -> dict[str, Any]:
        return {
            "date": trade_date,
            "side": side,
            "quantity": quantity,
            "price": price,
            "fee": fee,
            "action": decision["action"],
            "score": decision["overall_score"],
            "reason": "；".join(decision.get("notes", [])[:2]),
        }

    def _record_algorithm_diagnostic(self, diagnostics: dict[str, Any], algo, result: dict[str, Any], run_date) -> None:
        item = diagnostics["algorithms"].setdefault(
            algo.id,
            {"name": algo.name, "category": algo.category, "status": "ok", "warnings": 0, "errors": 0, "examples": []},
        )
        text = "；".join(result.get("reasons", []) + result.get("risks", []))
        warning_keywords = ["不足", "暂无", "不可得", "执行失败", "缺少"]
        if any(keyword in text for keyword in warning_keywords):
            item["warnings"] += 1
            if len(item["examples"]) < 5:
                item["examples"].append({"date": run_date, "step": "algorithm_data_check", "message": text[:240]})
            if item["status"] == "ok":
                item["status"] = "warning"

    def _record_trade_blocker(self, diagnostics: dict[str, Any], block_date, code: str, message: str) -> None:
        blockers = diagnostics["trade_blockers"]
        if len(blockers) < 20:
            blockers.append({"date": block_date, "code": code, "message": message})

    def _diagnostic_summary(self, diagnostics: dict[str, Any]) -> str:
        algos = diagnostics.get("algorithms", {})
        warnings = sum(1 for item in algos.values() if item.get("warnings", 0) > 0)
        errors = sum(1 for item in algos.values() if item.get("errors", 0) > 0)
        blockers = len(diagnostics.get("trade_blockers", []))
        return f"算法警告 {warnings} 个，算法错误 {errors} 个，交易阻塞 {blockers} 次。"

    def _summary(self, curve: list[dict[str, Any]], trades: list[dict[str, Any]], initial_cash: float, benchmark: list[float | None]) -> dict[str, Any]:
        final_equity = curve[-1]["equity"] if curve else initial_cash
        final_return = final_equity / initial_cash - 1 if initial_cash else 0
        peak = initial_cash
        max_drawdown = 0.0
        wins = 0
        completed = 0
        for row in curve:
            peak = max(peak, row["equity"])
            max_drawdown = min(max_drawdown, row["equity"] / peak - 1 if peak else 0)
            if row["daily_return"] != 0:
                completed += 1
                wins += 1 if row["daily_return"] > 0 else 0
        benchmark_values = [value for value in benchmark if value is not None]
        return {
            "final_equity": final_equity,
            "final_return": final_return,
            "benchmark_return": benchmark_values[-1] if benchmark_values else None,
            "excess_return": None if not benchmark_values else final_return - benchmark_values[-1],
            "max_drawdown": max_drawdown,
            "trade_count": len(trades),
            "win_rate": 0 if completed == 0 else wins / completed,
        }


def _period_return(close: pd.Series, days: int) -> float:
    if len(close) <= days:
        return 0.0
    base = close.iloc[-days - 1]
    return 0.0 if base == 0 else float((close.iloc[-1] - base) / base)


def _max_drawdown(close: pd.Series) -> float:
    peak = close.cummax()
    dd = close / peak - 1
    return float(dd.min()) if not dd.empty else 0.0


def _to_float(value) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None
