from __future__ import annotations

from datetime import date

from services.holding_service import HoldingService


def test_parse_time() -> None:
    value = HoldingService.parse_time("09:30")
    assert value is not None
    assert value.hour == 9
    assert value.minute == 30


def test_total_cost_idea() -> None:
    assert 10.5 * 100 + 2 == 1052
