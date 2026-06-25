from __future__ import annotations

from datetime import date

from database.models import AISignal
from services.memory_service import MemoryService


def _signal(action: str = "buy_candidate") -> AISignal:
    return AISignal(
        id=1,
        stock_code="600519",
        stock_name="贵州茅台",
        signal_date=date.today(),
        action=action,
        confidence=70,
        overall_score=72,
        trend_score=70,
        fundamental_score=60,
        valuation_score=55,
        capital_score=60,
        news_score=50,
        risk_score=65,
        suggested_position="20%",
    )


def test_memory_judges_failed_buy() -> None:
    service = MemoryService()
    assert service._judge_outcome("buy_candidate", -0.05, -0.08) == "failed"
    assert service._error_type("buy_candidate", -0.05, -0.08) == "weak_forward_return"


def test_memory_judges_over_conservative_filter() -> None:
    service = MemoryService()
    assert service._judge_outcome("avoid", 0.08, -0.03) == "failed"
    assert service._error_type("avoid", 0.08, -0.03) == "over_conservative_filter"


def test_memory_possible_causes() -> None:
    causes = MemoryService()._possible_causes(_signal(), -0.1, -0.15)
    assert causes
    assert any("风险" in cause for cause in causes)
