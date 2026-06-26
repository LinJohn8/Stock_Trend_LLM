from __future__ import annotations

from datetime import date

from database.db import init_db
from services.holding_service import HoldingService


def test_parse_time() -> None:
    value = HoldingService.parse_time("09:30")
    assert value is not None
    assert value.hour == 9
    assert value.minute == 30


def test_total_cost_idea() -> None:
    assert 10.5 * 100 + 2 == 1052


def test_update_current_quantity_status() -> None:
    init_db()
    service = HoldingService()
    item = service.add_holding("600519", "贵州茅台", date.today(), None, 100.0, 1000)
    partial = service.update_current_quantity(item.id, 500)
    assert partial is not None
    assert partial.current_quantity == 500
    assert partial.status == "partially_sold"
    sold = service.update_current_quantity(item.id, 0)
    assert sold is not None
    assert sold.current_quantity == 0
    assert sold.status == "sold"


def test_snapshot_updates_same_day(monkeypatch) -> None:
    init_db()
    monkeypatch.setattr("services.holding_service.StockDataService.get_latest_price", lambda self, stock_code: 110.0)
    service = HoldingService()
    item = service.add_holding("600519", "贵州茅台", date.today(), None, 100.0, 100)
    first = service.snapshot_holding(item)
    second = service.snapshot_holding(item)
    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert second.current_price == 110.0


def test_delete_holding_removes_snapshots(monkeypatch) -> None:
    from sqlalchemy import select

    from database.db import session_scope
    from database.models import Holding, HoldingSnapshot

    init_db()
    monkeypatch.setattr("services.holding_service.StockDataService.get_latest_price", lambda self, stock_code: 110.0)
    service = HoldingService()
    item = service.add_holding("600519", "贵州茅台", date.today(), None, 100.0, 100)
    snap = service.snapshot_holding(item)
    assert snap is not None

    assert service.delete_holding(item.id) is True

    with session_scope() as session:
        assert session.get(Holding, item.id) is None
        assert list(session.scalars(select(HoldingSnapshot).where(HoldingSnapshot.holding_id == item.id))) == []


def test_delete_holdings_batch(monkeypatch) -> None:
    from sqlalchemy import select

    from database.db import session_scope
    from database.models import Holding

    init_db()
    service = HoldingService()
    first = service.add_holding("600519", "贵州茅台", date.today(), None, 100.0, 100)
    second = service.add_holding("000001", "平安银行", date.today(), None, 10.0, 100)

    deleted = service.delete_holdings([first.id, second.id, second.id, 999999])

    assert deleted == 2
    with session_scope() as session:
        remaining = set(session.scalars(select(Holding.id).where(Holding.id.in_([first.id, second.id]))).all())
    assert remaining == set()
