from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select

from config.settings import get_settings
from database.db import session_scope
from database.models import AISignal, SignalTracking
from services.fundamental_service import FundamentalService
from services.indicator_service import IndicatorService
from services.memory_service import MemoryService
from services.risk_service import RiskService
from services.sentiment_service import SentimentService
from utils.math_utils import clamp
from utils.stock_utils import normalize_stock_code
from utils.time_utils import now_tz


VALID_ACTIONS = {"watch", "buy_candidate", "hold", "reduce", "sell", "avoid", "uncertain"}


class SignalService:
    """Rule-based explainable signal engine; AI summary can refine text later."""

    def analyze_stock(self, stock_code: str, stock_name: str = "", is_holding: bool = False, holding_profit_rate: float | None = None) -> dict:
        code = normalize_stock_code(stock_code)
        settings = get_settings()
        technical = IndicatorService().calculate(code)
        fundamental = FundamentalService().analyze(code)
        sentiment = SentimentService().analyze(code)
        risk = RiskService().evaluate(stock_name, technical, sentiment, holding_profit_rate)
        memory_adjustment = MemoryService().decision_adjustment(code)

        capital_score = _capital_score(technical)
        overall = (
            technical.get("trend_score", 50) * settings.technical_weight
            + fundamental["fundamental_score"] * settings.fundamental_weight
            + fundamental["valuation_score"] * settings.valuation_weight
            + capital_score * settings.capital_weight
            + sentiment["news_score"] * settings.news_weight
            + risk["risk_score"] * settings.risk_weight
        )
        overall = clamp(overall + memory_adjustment["net_score_adjustment"])
        action = _choose_action(overall, risk["risk_level"], is_holding, holding_profit_rate)
        if memory_adjustment["risk_penalty"] >= 12 and action == "buy_candidate":
            action = "watch"
        confidence = _confidence(overall, risk["risk_level"], technical)
        current_price = technical.get("current_price")
        suggested_position = _suggested_position(action, confidence, settings.max_suggested_position, risk["risk_level"])
        stop_loss = round(current_price * 0.92, 2) if current_price else None
        take_profit = round(current_price * 1.18, 2) if current_price else None

        reason = "；".join(
            [
                technical.get("technical_summary", "技术面不确定"),
                fundamental.get("fundamental_summary", "基本面不确定"),
                sentiment.get("news_summary", "消息面不确定"),
                "；".join(memory_adjustment["notes"]) if memory_adjustment["notes"] else "历史学习记忆暂无明显修正。",
            ]
        )
        invalidation = [
            "跌破 MA20 且放量时，短线判断需要重新评估。",
            "出现重大负面公告、监管风险或财报显著低于预期时，结论失效。",
            "大盘环境显著恶化时，降低买入或加仓等级。",
        ]
        signal = {
            "stock_code": code,
            "stock_name": stock_name,
            "signal_date": now_tz().date(),
            "current_price": current_price,
            "action": action,
            "confidence": confidence,
            "overall_score": overall,
            "trend_score": technical.get("trend_score", 50),
            "fundamental_score": fundamental["fundamental_score"],
            "valuation_score": fundamental["valuation_score"],
            "capital_score": capital_score,
            "news_score": sentiment["news_score"],
            "risk_score": risk["risk_score"],
            "risk_level": risk["risk_level"],
            "memory_adjustment": memory_adjustment,
            "reason": reason,
            "risk_points": risk["risk_points"],
            "invalidation_conditions": invalidation,
            "suggested_position": suggested_position,
            "stop_loss_price": stop_loss,
            "take_profit_price": take_profit,
            "ai_model": "rule_based_v1",
            "raw_ai_response": json.dumps({"technical": technical, "fundamental": fundamental, "sentiment": sentiment, "risk": risk, "memory_adjustment": memory_adjustment}, ensure_ascii=False, default=str),
        }
        if settings.ai_enabled:
            from services.ai_analysis_service import AIAnalysisService

            ai_signal = AIAnalysisService().analyze_single_stock(signal)
            signal.update(ai_signal)
            signal["ai_model"] = settings.ai_model
        saved = self.save_signal(signal)
        signal["id"] = saved.id
        return signal

    def save_signal(self, signal: dict) -> AISignal:
        action = signal.get("action", "uncertain")
        if action not in VALID_ACTIONS:
            action = "uncertain"
        with session_scope() as session:
            item = AISignal(
                stock_code=signal["stock_code"],
                stock_name=signal.get("stock_name", ""),
                signal_date=signal.get("signal_date", date.today()),
                current_price=signal.get("current_price"),
                action=action,
                confidence=signal.get("confidence", 50),
                overall_score=signal.get("overall_score", 50),
                trend_score=signal.get("trend_score", 50),
                fundamental_score=signal.get("fundamental_score", 50),
                valuation_score=signal.get("valuation_score", 50),
                capital_score=signal.get("capital_score", 50),
                news_score=signal.get("news_score", 50),
                risk_score=signal.get("risk_score", 50),
                reason=signal.get("reason", ""),
                risk_points=json.dumps(signal.get("risk_points", []), ensure_ascii=False),
                invalidation_conditions=json.dumps(signal.get("invalidation_conditions", []), ensure_ascii=False),
                suggested_position=signal.get("suggested_position", "0%"),
                stop_loss_price=signal.get("stop_loss_price"),
                take_profit_price=signal.get("take_profit_price"),
                ai_model=signal.get("ai_model", "rule_based_v1"),
                raw_ai_response=signal.get("raw_ai_response", ""),
            )
            session.add(item)
            session.flush()
            session.add(
                SignalTracking(
                    signal_id=item.id,
                    stock_code=item.stock_code,
                    signal_date=item.signal_date,
                    price_at_signal=item.current_price,
                )
            )
            session.refresh(item)
            return item

    def latest_signals(self, limit: int = 100) -> list[AISignal]:
        with session_scope() as session:
            return list(session.scalars(select(AISignal).order_by(AISignal.created_at.desc()).limit(limit)).all())


def _capital_score(technical: dict) -> float:
    score = 50
    vr = technical.get("volume_ratio")
    if vr and 0.8 <= vr <= 1.8:
        score += 15
    if vr and vr > 2.5 and technical.get("ret5", 0) < 0:
        score -= 15
    return clamp(score)


def _choose_action(overall: float, risk_level: str, is_holding: bool, holding_profit_rate: float | None) -> str:
    if risk_level == "high":
        if is_holding and holding_profit_rate is not None and holding_profit_rate < -0.08:
            return "reduce"
        return "avoid" if not is_holding else "reduce"
    if is_holding:
        if holding_profit_rate is not None and holding_profit_rate > 0.20:
            return "hold"
        if overall >= 55:
            return "hold"
        if overall < 45:
            return "reduce"
        return "uncertain"
    if overall >= 72 and risk_level == "low":
        return "buy_candidate"
    if overall >= 58:
        return "watch"
    if overall < 42:
        return "avoid"
    return "uncertain"


def _confidence(overall: float, risk_level: str, technical: dict) -> float:
    distance = abs(overall - 50)
    confidence = 45 + distance * 0.8
    if risk_level == "high":
        confidence -= 10
    if "历史行情不足" in technical.get("technical_summary", ""):
        confidence -= 15
    return clamp(confidence)


def _suggested_position(action: str, confidence: float, max_position: float, risk_level: str) -> str:
    if action not in {"buy_candidate", "hold"}:
        return "0%"
    fraction = min(max_position, max(0.1, confidence / 100 * max_position))
    if risk_level != "low":
        fraction = min(fraction, 0.1)
    return f"{fraction:.0%}"
