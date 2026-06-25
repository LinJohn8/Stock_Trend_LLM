from __future__ import annotations

from config.settings import get_settings
from utils.stock_utils import is_st_stock


class RiskService:
    def evaluate(self, stock_name: str, technical: dict, sentiment: dict, holding_profit_rate: float | None = None) -> dict:
        settings = get_settings()
        points: list[str] = []
        level = "low"
        action_limit = None

        if is_st_stock(stock_name):
            points.append("股票名称包含 ST/退，默认高风险。")
            level = "high"
        if technical.get("max_drawdown", 0) < -0.15:
            points.append("近 60 日最大回撤超过 15%。")
            level = "high"
        if technical.get("ma20") and technical.get("current_price") and technical["current_price"] < technical["ma20"] and technical.get("volume_ratio", 1) > 1.5:
            points.append("跌破 MA20 且成交量放大。")
            level = "high"
        if technical.get("ma60") and technical.get("current_price") and technical["current_price"] < technical["ma60"]:
            points.append("价格低于 MA60，趋势偏弱。")
            level = "medium" if level == "low" else level
        if technical.get("ret20", 0) > 0.30:
            points.append("近 20 日涨幅超过 30%，追高风险升高。")
            level = "medium" if level == "low" else level
        if sentiment.get("news_risk_level") == "high":
            points.append("消息面出现重大负面关键词。")
            level = "high"
        if holding_profit_rate is not None and holding_profit_rate <= settings.stop_loss_threshold:
            points.append(f"持仓亏损超过止损阈值 {settings.stop_loss_threshold:.0%}。")
            level = "high"
        if holding_profit_rate is not None and holding_profit_rate >= settings.take_profit_threshold:
            points.append(f"持仓盈利超过止盈提示阈值 {settings.take_profit_threshold:.0%}，可考虑移动止盈。")
            level = "medium" if level == "low" else level

        if level == "high":
            action_limit = "high_risk_no_buy"
        risk_score = {"low": 80, "medium": 55, "high": 25}[level]
        return {"risk_level": level, "risk_score": risk_score, "risk_points": points or ["暂无明确高风险触发项。"], "action_limit": action_limit}
