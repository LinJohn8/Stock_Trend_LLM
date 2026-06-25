from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from config.settings import get_settings
from database.db import session_scope
from database.models import AISignal, Holding, LearningMemory, StockSkillReview
from services.ai_analysis_service import AIAnalysisService
from services.fundamental_service import FundamentalService
from services.indicator_service import IndicatorService
from services.risk_service import RiskService
from services.sentiment_service import SentimentService
from services.stock_data_service import StockDataService
from utils.stock_utils import normalize_stock_code
from utils.time_utils import now_tz


@dataclass(frozen=True)
class LLMReviewSkill:
    id: str
    name: str
    description: str
    prompt_file: str


class LLMReviewSkillService:
    """LLM review skills that consume computed stock context snapshots."""

    SKILLS = [
        LLMReviewSkill(
            id="conservative_decision_review",
            name="1. 保守决策复核",
            description="从风控优先角度复核是否适合买入、持有、减仓或观望。",
            prompt_file="conservative_decision_review.md",
        ),
        LLMReviewSkill(
            id="technical_signal_explainer",
            name="2. 技术信号解释",
            description="解释均线、RSI、MACD、波动率、量价关系和关键触发条件。",
            prompt_file="technical_signal_explainer.md",
        ),
        LLMReviewSkill(
            id="news_risk_checker",
            name="3. 新闻风险核查",
            description="结合公告/新闻关键词、政策和行业不确定性，专门寻找反向风险。",
            prompt_file="news_risk_checker.md",
        ),
        LLMReviewSkill(
            id="learning_memory_reviewer",
            name="4. 历史错误记忆复盘",
            description="读取该股票历史学习记忆，提醒过去容易误判的模式。",
            prompt_file="learning_memory_reviewer.md",
        ),
    ]

    def list_skills(self) -> list[LLMReviewSkill]:
        return self.SKILLS

    def get_skill(self, skill_id: str) -> LLMReviewSkill:
        for skill in self.SKILLS:
            if skill.id == skill_id:
                return skill
        raise ValueError(f"未知 LLM Skill: {skill_id}")

    def build_computed_context(self, stock_code: str, stock_name: str = "") -> dict[str, Any]:
        code = normalize_stock_code(stock_code)
        data_service = StockDataService()
        df = data_service.get_daily_dataframe(code, limit=120)
        technical = IndicatorService().calculate(code)
        fundamental = FundamentalService().analyze(code)
        sentiment = SentimentService().analyze(code)
        risk = RiskService().evaluate(stock_name, technical, sentiment)
        latest_signal = self._latest_signal(code)
        holding_context = self._holding_context(code)
        memories = self._learning_memories(code)
        return {
            "stock_code": code,
            "stock_name": stock_name or (latest_signal or {}).get("stock_name", ""),
            "generated_at": now_tz().isoformat(),
            "recent_market_data": [] if df.empty else df.tail(30).to_dict("records"),
            "technical": technical,
            "fundamental": fundamental,
            "sentiment": sentiment,
            "risk": risk,
            "latest_signal": latest_signal,
            "holding": holding_context,
            "learning_memories": memories,
            "boundary": {
                "no_profit_promise": True,
                "no_auto_trading": True,
                "human_final_decision": True,
                "high_risk_no_strong_buy": True,
            },
        }

    def run_skill(self, stock_code: str, skill_id: str, stock_name: str = "") -> StockSkillReview:
        skill = self.get_skill(skill_id)
        context = self.build_computed_context(stock_code, stock_name)
        prompt = self._prompt(skill)
        result = AIAnalysisService().complete_skill_review(prompt, context)
        settings = get_settings()
        with session_scope() as session:
            item = StockSkillReview(
                stock_code=context["stock_code"],
                stock_name=context.get("stock_name", ""),
                skill_id=skill.id,
                skill_name=skill.name,
                review_date=now_tz().date(),
                input_snapshot=json.dumps(context, ensure_ascii=False, default=str),
                result_text=result,
                ai_provider=settings.ai_provider if settings.ai_enabled else "local_fallback",
                ai_model=settings.ai_model if settings.ai_enabled else "rule_based_fallback",
            )
            session.add(item)
            session.flush()
            session.refresh(item)
            return item

    def list_reviews(self, stock_code: str | None = None, limit: int = 100) -> list[StockSkillReview]:
        with session_scope() as session:
            stmt = select(StockSkillReview).order_by(StockSkillReview.created_at.desc()).limit(limit)
            if stock_code:
                stmt = stmt.where(StockSkillReview.stock_code == normalize_stock_code(stock_code))
            return list(session.scalars(stmt).all())

    def _prompt(self, skill: LLMReviewSkill) -> str:
        path = Path(__file__).resolve().parents[1] / "ai" / "llm_skills" / skill.prompt_file
        return path.read_text(encoding="utf-8")

    def _latest_signal(self, stock_code: str) -> dict[str, Any] | None:
        with session_scope() as session:
            signal = session.scalar(
                select(AISignal)
                .where(AISignal.stock_code == stock_code)
                .order_by(AISignal.created_at.desc())
            )
            if not signal:
                return None
            return {
                "id": signal.id,
                "stock_code": signal.stock_code,
                "stock_name": signal.stock_name,
                "signal_date": signal.signal_date,
                "current_price": signal.current_price,
                "action": signal.action,
                "confidence": signal.confidence,
                "overall_score": signal.overall_score,
                "trend_score": signal.trend_score,
                "fundamental_score": signal.fundamental_score,
                "valuation_score": signal.valuation_score,
                "capital_score": signal.capital_score,
                "news_score": signal.news_score,
                "risk_score": signal.risk_score,
                "reason": signal.reason,
                "risk_points": signal.risk_points,
                "invalidation_conditions": signal.invalidation_conditions,
                "suggested_position": signal.suggested_position,
                "stop_loss_price": signal.stop_loss_price,
                "take_profit_price": signal.take_profit_price,
            }

    def _holding_context(self, stock_code: str) -> dict[str, Any] | None:
        with session_scope() as session:
            holding = session.scalar(
                select(Holding)
                .where(Holding.stock_code == stock_code, Holding.status.in_(["holding", "partially_sold", "watching"]))
                .order_by(Holding.created_at.desc())
            )
            if not holding:
                return None
            return {
                "id": holding.id,
                "stock_code": holding.stock_code,
                "stock_name": holding.stock_name,
                "buy_date": holding.buy_date,
                "buy_price": holding.buy_price,
                "quantity": holding.quantity,
                "current_quantity": holding.current_quantity,
                "total_cost": holding.total_cost,
                "buy_reason": holding.buy_reason,
                "source_info": holding.source_info,
                "is_real_position": holding.is_real_position,
                "status": holding.status,
            }

    def _learning_memories(self, stock_code: str) -> list[dict[str, Any]]:
        with session_scope() as session:
            memories = list(
                session.scalars(
                    select(LearningMemory)
                    .where(LearningMemory.stock_code == stock_code)
                    .order_by(LearningMemory.created_at.desc())
                    .limit(8)
                )
            )
            return [
                {
                    "id": item.id,
                    "review_date": item.review_date,
                    "horizon_days": item.horizon_days,
                    "original_action": item.original_action,
                    "actual_return": item.actual_return,
                    "max_drawdown": item.max_drawdown,
                    "outcome": item.outcome,
                    "error_type": item.error_type,
                    "possible_causes": item.possible_causes,
                    "lesson": item.lesson,
                    "proposed_changes": item.proposed_changes,
                    "status": item.status,
                }
                for item in memories
            ]
