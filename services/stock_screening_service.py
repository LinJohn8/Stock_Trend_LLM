from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from data_sources.akshare_client import AKShareClient
from services.stock_data_service import StockDataService
from utils.math_utils import clamp
from utils.stock_utils import normalize_stock_code


@dataclass(frozen=True)
class ScreeningConfig:
    cash: float
    max_candidates: int = 80
    enrich_top: int = 24
    exclude_st: bool = True
    min_amount: float = 0


class StockScreeningService:
    """Find one-lot-affordable A-share candidates and rank them with explainable signals."""

    def __init__(self) -> None:
        self.client = AKShareClient()
        self.data_service = StockDataService()

    def screen_affordable(self, config: ScreeningConfig) -> dict[str, Any]:
        one_lot_price_limit = max(0.0, float(config.cash)) / 100
        realtime = self.client.get_realtime()
        if realtime.empty:
            return {
                "cash": config.cash,
                "one_lot_price_limit": one_lot_price_limit,
                "source": "unavailable",
                "total_rows": 0,
                "affordable_rows": 0,
                "results": [],
                "diagnostics": ["未能获取全市场实时行情表。请检查网络、AKShare/Eastmoney 接口或稍后重试。"],
            }

        df = self._normalize_realtime(realtime)
        total_rows = len(df)
        df = df[(df["current_price"] > 0) & (df["current_price"] <= one_lot_price_limit)]
        if config.exclude_st and "stock_name" in df:
            df = df[~df["stock_name"].astype(str).str.upper().str.contains("ST", na=False)]
        if config.min_amount > 0 and "amount" in df:
            df = df[df["amount"].fillna(0) >= config.min_amount]
        affordable_rows = len(df)
        df = df.sort_values(["amount", "turnover_rate"], ascending=False, na_position="last").head(max(1, config.max_candidates))

        rows: list[dict[str, Any]] = []
        diagnostics: list[str] = []
        for idx, row in enumerate(df.to_dict("records")):
            enriched = idx < max(0, config.enrich_top)
            scored = self._score_row(row, enriched=enriched)
            rows.append(scored)
            if enriched and scored.get("data_warning"):
                diagnostics.append(f"{scored['stock_code']} {scored['stock_name']}：{scored['data_warning']}")

        rows.sort(key=lambda item: (item["score"], item["confidence"], item.get("amount") or 0), reverse=True)
        return {
            "cash": config.cash,
            "one_lot_price_limit": one_lot_price_limit,
            "source": self._source_label(realtime),
            "total_rows": total_rows,
            "affordable_rows": affordable_rows,
            "results": rows,
            "diagnostics": diagnostics[:20],
        }

    def _normalize_realtime(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        if "stock_code" not in data.columns and "代码" in data.columns:
            data = data.rename(columns={"代码": "stock_code"})
        if "stock_name" not in data.columns and "名称" in data.columns:
            data = data.rename(columns={"名称": "stock_name"})
        data["stock_code"] = data["stock_code"].astype(str).str.extract(r"(\d{6})", expand=False).fillna("").map(normalize_stock_code)
        for col in ["current_price", "pct_change", "change_amount", "amount", "volume", "volume_ratio", "turnover_rate", "pe", "pb"]:
            if col not in data.columns:
                data[col] = None
            data[col] = pd.to_numeric(data[col], errors="coerce")
        if "stock_name" not in data.columns:
            data["stock_name"] = ""
        return data[data["stock_code"].str.len() == 6].reset_index(drop=True)

    def _score_row(self, row: dict[str, Any], *, enriched: bool) -> dict[str, Any]:
        code = normalize_stock_code(row.get("stock_code", ""))
        price = _float(row.get("current_price")) or 0.0
        pct = _float(row.get("pct_change"))
        amount = _float(row.get("amount"))
        turnover = _float(row.get("turnover_rate"))
        volume_ratio = _float(row.get("volume_ratio"))
        pe = _float(row.get("pe"))
        pb = _float(row.get("pb"))

        score = 50.0
        confidence = 48.0
        reasons: list[str] = []
        risks: list[str] = []
        data_warning = ""

        if pct is not None:
            if -2.5 <= pct <= 4.5:
                score += 8
                reasons.append(f"当日涨跌幅 {pct:.2f}%，未明显过热或崩跌。")
            elif pct > 6:
                score -= 10
                risks.append(f"当日涨幅 {pct:.2f}% 偏高，追高风险上升。")
            elif pct < -5:
                score -= 12
                risks.append(f"当日跌幅 {pct:.2f}% 较大，需要确认是否有负面事件。")
        if amount is not None:
            if amount >= 300_000_000:
                score += 8
                confidence += 8
                reasons.append("成交额较高，流动性相对更好。")
            elif amount < 30_000_000:
                score -= 8
                risks.append("成交额偏低，买卖冲击和滑点风险更高。")
        if turnover is not None:
            if 1 <= turnover <= 8:
                score += 5
                reasons.append(f"换手率 {turnover:.2f}% 处于相对可观察区间。")
            elif turnover > 15:
                score -= 6
                risks.append(f"换手率 {turnover:.2f}% 偏高，短线博弈较重。")
        if volume_ratio is not None:
            if 0.8 <= volume_ratio <= 2.2:
                score += 4
            elif volume_ratio > 3:
                score -= 6
                risks.append(f"量比 {volume_ratio:.2f} 偏高，需要确认放量方向。")
        if pe is not None and pe > 0:
            if pe <= 45:
                score += 4
            elif pe > 100:
                score -= 7
                risks.append(f"动态 PE {pe:.1f} 偏高。")
        if pb is not None and pb > 0:
            if pb <= 4:
                score += 3
            elif pb > 10:
                score -= 5
                risks.append(f"PB {pb:.1f} 偏高。")

        if enriched:
            technical = self._daily_enrichment(code)
            score += technical["score_delta"]
            confidence += technical["confidence_delta"]
            reasons.extend(technical["reasons"])
            risks.extend(technical["risks"])
            data_warning = technical["warning"]

        action = "buy_candidate" if score >= 72 and not any("跌幅" in risk or "流动性" in risk for risk in risks) else "watch" if score >= 58 else "avoid" if score < 42 else "uncertain"
        return {
            "stock_code": code,
            "stock_name": str(row.get("stock_name") or ""),
            "current_price": price,
            "one_lot_cost": price * 100,
            "pct_change": pct,
            "amount": amount,
            "turnover_rate": turnover,
            "volume_ratio": volume_ratio,
            "pe": pe,
            "pb": pb,
            "score": round(clamp(score), 1),
            "confidence": round(clamp(confidence), 1),
            "action": action,
            "reasons": reasons[:5] or ["满足一手资金过滤，等待进一步行情/新闻/算法确认。"],
            "risks": risks[:5] or ["未发现实时表层面的明显风险，但仍需进入工作台做新闻和历史走势复核。"],
            "data_warning": data_warning,
        }

    def _daily_enrichment(self, stock_code: str) -> dict[str, Any]:
        try:
            if not self.data_service.has_recent_daily_data(stock_code, min_rows=40):
                self.data_service.update_daily_data(stock_code, days=180)
            daily = self.data_service.get_daily_dataframe(stock_code, limit=90)
        except Exception as exc:
            return {"score_delta": 0, "confidence_delta": -8, "reasons": [], "risks": [], "warning": f"日线补充失败：{exc}"}
        if daily.empty or len(daily) < 30:
            return {"score_delta": 0, "confidence_delta": -10, "reasons": [], "risks": [], "warning": "日线样本不足，未纳入趋势强化评分。"}
        close = daily["close"].astype(float)
        latest = close.iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else None
        ret20 = 0.0 if len(close) <= 20 or close.iloc[-21] == 0 else latest / close.iloc[-21] - 1
        drawdown = (close / close.cummax() - 1).tail(60).min()
        score_delta = 0.0
        confidence_delta = 10.0
        reasons: list[str] = []
        risks: list[str] = []
        if ma20 and latest >= ma20:
            score_delta += 7
            reasons.append("收盘价站上 MA20，短中期趋势更健康。")
        elif ma20:
            score_delta -= 8
            risks.append("收盘价低于 MA20，趋势确认不足。")
        if ma60 and latest >= ma60:
            score_delta += 5
            reasons.append("收盘价站上 MA60，中期结构较稳。")
        if ret20 > 0.18:
            score_delta -= 5
            risks.append(f"近 20 日涨幅 {ret20:.2%} 偏高。")
        elif 0.02 <= ret20 <= 0.15:
            score_delta += 5
            reasons.append(f"近 20 日收益 {ret20:.2%}，动量温和。")
        if drawdown <= -0.20:
            score_delta -= 8
            risks.append(f"近 60 日最大回撤 {drawdown:.2%}，风险承受要求较高。")
        return {"score_delta": score_delta, "confidence_delta": confidence_delta, "reasons": reasons, "risks": risks, "warning": ""}

    def _source_label(self, df: pd.DataFrame) -> str:
        if "source" in df.columns:
            values = [str(item) for item in df["source"].dropna().unique().tolist()[:3]]
            if values:
                return ",".join(values)
        return "akshare_eastmoney_realtime"


def _float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None
