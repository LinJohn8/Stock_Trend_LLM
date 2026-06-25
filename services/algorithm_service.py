from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import select

from database.db import session_scope
from database.models import AlgorithmRun, Holding, LearningMemory
from services.fundamental_service import FundamentalService
from services.indicator_service import IndicatorService
from services.risk_service import RiskService
from services.sentiment_service import SentimentService
from services.stock_data_service import StockDataService
from utils.math_utils import clamp
from utils.stock_utils import normalize_stock_code
from utils.time_utils import now_tz


@dataclass(frozen=True)
class AnalysisAlgorithm:
    id: str
    name: str
    description: str
    weight: float
    runner: Callable[[dict[str, Any]], dict[str, Any]]


class AlgorithmService:
    """Selectable deterministic analysis algorithms for dashboard use."""

    def list_algorithms(self) -> list[AnalysisAlgorithm]:
        return [
            AnalysisAlgorithm("trend_following", "趋势跟踪", "均线结构、价格位置和趋势延续性。", 0.22, self._trend_following),
            AnalysisAlgorithm("momentum", "动量强弱", "近 5/20/60 日收益、RSI、MACD。", 0.16, self._momentum),
            AnalysisAlgorithm("mean_reversion", "回撤修复", "超跌、偏离均线、波动收敛后的修复可能性。", 0.10, self._mean_reversion),
            AnalysisAlgorithm("valuation", "估值检查", "PE/PB 与第一版估值安全边际。", 0.14, self._valuation),
            AnalysisAlgorithm("capital_volume", "资金量价", "成交量、量比、放量方向和换手风险。", 0.14, self._capital_volume),
            AnalysisAlgorithm("news_risk", "新闻风险", "公告/新闻关键词、负面事件和不确定性。", 0.12, self._news_risk),
            AnalysisAlgorithm("holding_review", "持仓复核", "持仓盈亏、止损止盈、买入逻辑是否仍成立。", 0.08, self._holding_review),
            AnalysisAlgorithm("learning_memory", "历史记忆", "历史错误复盘中反复出现的问题。", 0.04, self._learning_memory),
        ]

    def run(
        self,
        stock_code: str,
        stock_name: str = "",
        selected_algorithm_ids: list[str] | None = None,
        fetch_data: bool = True,
    ) -> dict[str, Any]:
        code = normalize_stock_code(stock_code)
        if fetch_data:
            StockDataService().update_daily_data(code)
        context = self._build_context(code, stock_name)
        algorithms = self.list_algorithms()
        if selected_algorithm_ids:
            selected = [algo for algo in algorithms if algo.id in set(selected_algorithm_ids)]
        else:
            selected = algorithms
        results = [algo.runner(context) | {"id": algo.id, "name": algo.name, "weight": algo.weight} for algo in selected]
        overall_score = self._weighted_score(results)
        action = self._action(overall_score, results)
        confidence = self._confidence(overall_score, results)
        output = {
            "stock_code": code,
            "stock_name": stock_name,
            "run_date": now_tz().date(),
            "selected_algorithms": [algo.id for algo in selected],
            "overall_score": overall_score,
            "action": action,
            "confidence": confidence,
            "results": results,
            "summary": self._summary(action, overall_score, results),
            "disclaimer": "仅用于个人研究和辅助决策，不构成投资建议。",
        }
        self.save_run(output)
        return output

    def save_run(self, output: dict[str, Any]) -> AlgorithmRun:
        with session_scope() as session:
            item = AlgorithmRun(
                stock_code=output["stock_code"],
                stock_name=output.get("stock_name", ""),
                run_date=output["run_date"],
                selected_algorithms=json.dumps(output["selected_algorithms"], ensure_ascii=False),
                result_json=json.dumps(output, ensure_ascii=False, default=str),
                overall_score=output["overall_score"],
                action=output["action"],
                confidence=output["confidence"],
            )
            session.add(item)
            session.flush()
            session.refresh(item)
            return item

    def list_runs(self, stock_code: str | None = None, limit: int = 100) -> list[AlgorithmRun]:
        with session_scope() as session:
            stmt = select(AlgorithmRun).order_by(AlgorithmRun.created_at.desc()).limit(limit)
            if stock_code:
                stmt = stmt.where(AlgorithmRun.stock_code == normalize_stock_code(stock_code))
            return list(session.scalars(stmt).all())

    def _build_context(self, stock_code: str, stock_name: str) -> dict[str, Any]:
        technical = IndicatorService().calculate(stock_code)
        fundamental = FundamentalService().analyze(stock_code)
        sentiment = SentimentService().analyze(stock_code)
        risk = RiskService().evaluate(stock_name, technical, sentiment, self._holding_profit_rate(stock_code))
        df = StockDataService().get_daily_dataframe(stock_code, limit=120)
        return {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "technical": technical,
            "fundamental": fundamental,
            "sentiment": sentiment,
            "risk": risk,
            "daily": df,
            "holding": self._holding(stock_code),
            "memories": self._memories(stock_code),
        }

    def _trend_following(self, ctx: dict[str, Any]) -> dict[str, Any]:
        t = ctx["technical"]
        score = t.get("trend_score", 50)
        reasons = [t.get("technical_summary", "技术面数据不足。")]
        if t.get("current_price") and t.get("ma20") and t["current_price"] < t["ma20"]:
            reasons.append("价格低于 MA20，趋势跟踪算法降低评分。")
        return {"score": clamp(score), "view": "trend", "reasons": reasons, "risks": []}

    def _momentum(self, ctx: dict[str, Any]) -> dict[str, Any]:
        t = ctx["technical"]
        score = t.get("momentum_score", 50)
        risks = []
        if t.get("rsi") and t["rsi"] > 75:
            risks.append("RSI 偏高，短线过热。")
        if t.get("ret20", 0) > 0.30:
            risks.append("近 20 日涨幅过大，追高风险增加。")
        return {"score": clamp(score), "view": "momentum", "reasons": [f"近20日收益 {t.get('ret20', 0):.2%}，RSI {t.get('rsi') or '-'}。"], "risks": risks}

    def _mean_reversion(self, ctx: dict[str, Any]) -> dict[str, Any]:
        t = ctx["technical"]
        score = 50
        reasons = []
        if t.get("rsi") and t["rsi"] < 35:
            score += 15
            reasons.append("RSI 较低，存在超跌修复观察价值。")
        if t.get("max_drawdown", 0) < -0.15:
            score += 8
            reasons.append("近期回撤较大，但需要确认风险释放是否结束。")
        if t.get("current_price") and t.get("ma60") and t["current_price"] < t["ma60"]:
            score -= 12
            reasons.append("价格仍低于 MA60，修复交易需要更谨慎。")
        return {"score": clamp(score), "view": "mean_reversion", "reasons": reasons or ["未出现明显均值回归信号。"], "risks": ["超跌不等于反转，需要等待确认。"]}

    def _valuation(self, ctx: dict[str, Any]) -> dict[str, Any]:
        f = ctx["fundamental"]
        score = f.get("valuation_score", 50)
        risks = []
        if f.get("pe") and f["pe"] > 80:
            risks.append("PE 偏高，估值安全边际不足。")
        return {"score": clamp(score), "view": "valuation", "reasons": [f.get("fundamental_summary", "估值数据不足。")], "risks": risks}

    def _capital_volume(self, ctx: dict[str, Any]) -> dict[str, Any]:
        t = ctx["technical"]
        score = 50
        reasons = []
        risks = []
        vr = t.get("volume_ratio")
        if vr and 0.8 <= vr <= 1.8:
            score += 12
            reasons.append("量比相对温和，未见异常放量。")
        if vr and vr > 2 and t.get("ret5", 0) < 0:
            score -= 18
            risks.append("放量下跌，资金面需谨慎。")
        return {"score": clamp(score), "view": "capital_volume", "reasons": reasons or [f"量比 {vr or '-'}。"], "risks": risks}

    def _news_risk(self, ctx: dict[str, Any]) -> dict[str, Any]:
        s = ctx["sentiment"]
        score = s.get("news_score", 50)
        risks = []
        if s.get("news_risk_level") != "low":
            risks.append(s.get("news_summary", "消息面不确定。"))
        return {"score": clamp(score), "view": "news_risk", "reasons": [s.get("news_summary", "暂无消息面数据。")], "risks": risks}

    def _holding_review(self, ctx: dict[str, Any]) -> dict[str, Any]:
        holding = ctx.get("holding")
        if not holding:
            return {"score": 50, "view": "holding_review", "reasons": ["未记录持仓，此算法仅作中性处理。"], "risks": []}
        profit = holding.get("profit_rate")
        score = 55
        risks = []
        if profit is not None and profit <= -0.08:
            score -= 25
            risks.append("持仓亏损超过 -8%，触发止损复核。")
        if profit is not None and profit >= 0.20:
            risks.append("持仓盈利超过 20%，建议考虑移动止盈。")
        return {"score": clamp(score), "view": "holding_review", "reasons": [f"当前持仓收益 {profit:.2%}" if profit is not None else "持仓收益暂不可得。"], "risks": risks}

    def _learning_memory(self, ctx: dict[str, Any]) -> dict[str, Any]:
        memories = ctx.get("memories", [])
        if not memories:
            return {"score": 50, "view": "learning_memory", "reasons": ["暂无该股票历史学习记忆。"], "risks": []}
        open_failures = [m for m in memories if m.get("outcome") == "failed" and m.get("status") != "ignored"]
        score = 50 - min(20, len(open_failures) * 5)
        return {
            "score": clamp(score),
            "view": "learning_memory",
            "reasons": [f"找到 {len(memories)} 条历史记忆，其中未忽略失败样本 {len(open_failures)} 条。"],
            "risks": [m.get("lesson", "") for m in open_failures[:3]],
        }

    def _weighted_score(self, results: list[dict[str, Any]]) -> float:
        if not results:
            return 50
        total_weight = sum(item["weight"] for item in results) or 1
        return clamp(sum(item["score"] * item["weight"] for item in results) / total_weight)

    def _action(self, score: float, results: list[dict[str, Any]]) -> str:
        risk_text = " ".join(" ".join(item.get("risks", [])) for item in results)
        if any(key in risk_text for key in ["止损", "放量下跌", "高风险"]):
            return "reduce"
        if score >= 72:
            return "buy_candidate"
        if score >= 58:
            return "watch"
        if score < 42:
            return "avoid"
        return "uncertain"

    def _confidence(self, score: float, results: list[dict[str, Any]]) -> float:
        dispersion = 0
        if results:
            avg = sum(item["score"] for item in results) / len(results)
            dispersion = sum(abs(item["score"] - avg) for item in results) / len(results)
        return clamp(45 + abs(score - 50) * 0.7 - dispersion * 0.2)

    def _summary(self, action: str, score: float, results: list[dict[str, Any]]) -> str:
        top_risks = [risk for item in results for risk in item.get("risks", [])][:3]
        risk_text = "；".join(top_risks) if top_risks else "暂无明确高风险触发项。"
        return f"算法组合动作为 {action}，综合评分 {score:.1f}。主要风险：{risk_text}"

    def _holding(self, stock_code: str) -> dict[str, Any] | None:
        with session_scope() as session:
            holding = session.scalar(
                select(Holding)
                .where(Holding.stock_code == stock_code, Holding.status.in_(["holding", "partially_sold", "watching"]))
                .order_by(Holding.created_at.desc())
            )
            if not holding:
                return None
            current_price = StockDataService().get_latest_price(stock_code)
            profit_rate = None
            if current_price and holding.buy_price:
                profit_rate = (current_price - holding.buy_price) / holding.buy_price
            return {
                "id": holding.id,
                "buy_price": holding.buy_price,
                "current_quantity": holding.current_quantity,
                "profit_rate": profit_rate,
                "buy_reason": holding.buy_reason,
                "status": holding.status,
            }

    def _holding_profit_rate(self, stock_code: str) -> float | None:
        holding = self._holding(stock_code)
        return None if not holding else holding.get("profit_rate")

    def _memories(self, stock_code: str) -> list[dict[str, Any]]:
        with session_scope() as session:
            memories = list(
                session.scalars(
                    select(LearningMemory)
                    .where(LearningMemory.stock_code == stock_code)
                    .order_by(LearningMemory.created_at.desc())
                    .limit(20)
                )
            )
            return [
                {
                    "id": item.id,
                    "outcome": item.outcome,
                    "error_type": item.error_type,
                    "lesson": item.lesson,
                    "status": item.status,
                }
                for item in memories
            ]
