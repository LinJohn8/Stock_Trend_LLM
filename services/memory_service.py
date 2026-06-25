from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select

from database.db import session_scope
from database.models import AISignal, LearningMemory, SignalTracking
from utils.time_utils import now_tz


class MemoryService:
    """Create auditable learning records from paper-trading outcomes."""

    REVIEW_HORIZONS = {
        1: "return_1d",
        5: "return_5d",
        20: "return_20d",
        60: "return_60d",
    }

    def generate_learning_memories(self, include_success: bool = False) -> int:
        """Review tracked signals and persist lessons for failures or all outcomes."""
        created_or_updated = 0
        with session_scope() as session:
            tracks = list(session.scalars(select(SignalTracking)).all())
            for track in tracks:
                signal = session.get(AISignal, track.signal_id)
                if not signal:
                    continue
                for horizon, attr in self.REVIEW_HORIZONS.items():
                    actual_return = getattr(track, attr)
                    if actual_return is None:
                        continue
                    outcome = self._judge_outcome(signal.action, actual_return, track.max_drawdown_after_signal)
                    if outcome == "success" and not include_success:
                        continue
                    memory = session.scalar(
                        select(LearningMemory).where(
                            LearningMemory.signal_id == signal.id,
                            LearningMemory.horizon_days == horizon,
                        )
                    )
                    payload = self._build_memory(signal, track, horizon, actual_return, outcome)
                    if memory:
                        payload.pop("status", None)
                        for key, value in payload.items():
                            setattr(memory, key, value)
                    else:
                        session.add(LearningMemory(**payload))
                    created_or_updated += 1
        return created_or_updated

    def list_memories(self, status: str | None = None, limit: int = 200) -> list[LearningMemory]:
        with session_scope() as session:
            stmt = select(LearningMemory).order_by(LearningMemory.created_at.desc()).limit(limit)
            if status:
                stmt = stmt.where(LearningMemory.status == status)
            return list(session.scalars(stmt).all())

    def mark_status(self, memory_id: int, status: str) -> None:
        if status not in {"open", "reviewed", "applied", "ignored"}:
            raise ValueError("status must be open/reviewed/applied/ignored")
        with session_scope() as session:
            item = session.get(LearningMemory, memory_id)
            if item:
                item.status = status

    def stats(self) -> dict:
        memories = self.list_memories(limit=10_000)
        by_type: dict[str, int] = {}
        by_action: dict[str, int] = {}
        for memory in memories:
            by_type[memory.error_type or memory.outcome] = by_type.get(memory.error_type or memory.outcome, 0) + 1
            by_action[memory.original_action] = by_action.get(memory.original_action, 0) + 1
        return {
            "total": len(memories),
            "open": sum(1 for m in memories if m.status == "open"),
            "applied": sum(1 for m in memories if m.status == "applied"),
            "by_type": by_type,
            "by_action": by_action,
        }

    def _build_memory(
        self,
        signal: AISignal,
        track: SignalTracking,
        horizon: int,
        actual_return: float,
        outcome: str,
    ) -> dict:
        error_type = self._error_type(signal.action, actual_return, track.max_drawdown_after_signal)
        possible_causes = self._possible_causes(signal, actual_return, track.max_drawdown_after_signal)
        proposed_changes = self._proposed_changes(error_type, signal)
        evidence = {
            "overall_score": signal.overall_score,
            "trend_score": signal.trend_score,
            "fundamental_score": signal.fundamental_score,
            "valuation_score": signal.valuation_score,
            "capital_score": signal.capital_score,
            "news_score": signal.news_score,
            "risk_score": signal.risk_score,
            "suggested_position": signal.suggested_position,
            "stop_loss_price": signal.stop_loss_price,
            "take_profit_price": signal.take_profit_price,
            "reason": signal.reason,
            "risk_points": signal.risk_points,
            "invalidation_conditions": signal.invalidation_conditions,
        }
        lesson = self._lesson(signal.action, horizon, actual_return, error_type)
        return {
            "signal_id": signal.id,
            "stock_code": signal.stock_code,
            "stock_name": signal.stock_name,
            "review_date": now_tz().date(),
            "signal_date": signal.signal_date,
            "horizon_days": horizon,
            "original_action": signal.action,
            "confidence": signal.confidence,
            "price_at_signal": track.price_at_signal,
            "actual_return": actual_return,
            "max_drawdown": track.max_drawdown_after_signal,
            "benchmark_return": track.benchmark_return,
            "outcome": outcome,
            "error_type": error_type,
            "possible_causes": json.dumps(possible_causes, ensure_ascii=False),
            "evidence_snapshot": json.dumps(evidence, ensure_ascii=False, default=str),
            "lesson": lesson,
            "proposed_changes": json.dumps(proposed_changes, ensure_ascii=False),
            "status": "open",
        }

    def _judge_outcome(self, action: str, actual_return: float, max_drawdown: float | None) -> str:
        if action in {"buy_candidate", "hold", "watch"}:
            if actual_return > 0 and (max_drawdown is None or max_drawdown > -0.12):
                return "success"
            return "failed"
        if action in {"reduce", "sell", "avoid"}:
            return "success" if actual_return <= 0 else "failed"
        return "uncertain"

    def _error_type(self, action: str, actual_return: float, max_drawdown: float | None) -> str:
        if action in {"buy_candidate", "hold", "watch"} and actual_return < 0:
            if max_drawdown is not None and max_drawdown <= -0.12:
                return "missed_downside_risk"
            return "weak_forward_return"
        if action in {"reduce", "sell", "avoid"} and actual_return > 0:
            return "over_conservative_filter"
        return "uncertain_or_mixed_result"

    def _possible_causes(self, signal: AISignal, actual_return: float, max_drawdown: float | None) -> list[str]:
        causes: list[str] = []
        if signal.action in {"buy_candidate", "hold", "watch"} and actual_return < 0:
            if signal.trend_score >= 65:
                causes.append("趋势评分可能过度依赖均线位置，未充分识别趋势衰竭。")
            if signal.risk_score >= 55 and max_drawdown is not None and max_drawdown <= -0.12:
                causes.append("风险评分偏乐观，最大回撤触发后应提高风险权重。")
            if signal.news_score >= 50:
                causes.append("消息面数据可能不足，负面公告/新闻接口需要补强。")
            if signal.capital_score >= 55:
                causes.append("资金面评分可能未区分放量上涨和放量下跌后的持续性。")
            causes.append("需要复核当时大盘和行业环境，当前第一版市场环境数据仍较粗。")
        elif signal.action in {"reduce", "sell", "avoid"} and actual_return > 0:
            if signal.risk_score < 35:
                causes.append("风险规则可能过于保守，错过高波动修复行情。")
            causes.append("可能存在突发利好、行业政策或资金回流，新闻和行业数据需要补强。")
            causes.append("回避/减仓类动作需要增加反向确认条件，避免单一风险信号触发。")
        else:
            causes.append("结果不明确，需要更长周期或更多样本确认。")
        return causes

    def _proposed_changes(self, error_type: str, signal: AISignal) -> list[str]:
        if error_type == "missed_downside_risk":
            return [
                "提高近 20/60 日最大回撤和跌破 MA20 放量的风险权重。",
                "买入候选必须同时满足风险评分和资金面方向确认。",
                "增加行业指数和沪深300环境过滤。",
            ]
        if error_type == "weak_forward_return":
            return [
                "降低弱趋势或低成交量股票的 suggested_position。",
                "增加买入后 5 日不及预期的重新评估规则。",
            ]
        if error_type == "over_conservative_filter":
            return [
                "为高风险但基本面未恶化的股票增加 watch 而非 avoid 的中间状态。",
                "增加利好公告、行业政策、资金回流的反向条件识别。",
            ]
        return ["保留样本，等待更多同类记录后再调整规则。"]

    def _lesson(self, action: str, horizon: int, actual_return: float, error_type: str) -> str:
        return (
            f"原始动作 {action} 在 {horizon} 日后收益为 {actual_return:.2%}，"
            f"复盘类型为 {error_type}。后续规则更新应优先检查该类样本是否重复出现。"
        )
