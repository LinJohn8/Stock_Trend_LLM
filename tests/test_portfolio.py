from __future__ import annotations

from database.db import init_db
from services.portfolio_service import PortfolioService


def test_watchlist_crud_and_delete() -> None:
    init_db()
    service = PortfolioService()
    item = service.add_watchlist("600519", "贵州茅台", "白酒", "note", "tag")

    updated = service.update_watchlist(item.stock_code, stock_name="茅台", industry="消费", is_active=False)

    assert updated is not None
    assert updated.stock_name == "茅台"
    assert updated.industry == "消费"
    assert updated.is_active is False
    assert service.deactivate_watchlist(item.stock_code) is True
    assert service.delete_watchlist(item.stock_code) is True
    assert service.delete_watchlist(item.stock_code) is False


def test_watchlist_batch_delete() -> None:
    init_db()
    service = PortfolioService()
    first = service.add_watchlist("000001", "平安银行")
    second = service.add_watchlist("300750", "宁德时代")

    deleted = service.delete_watchlist_many([first.stock_code, second.stock_code, second.stock_code, "999999"])

    assert deleted == 2
    remaining = {item.stock_code for item in service.list_watchlist()}
    assert first.stock_code not in remaining
    assert second.stock_code not in remaining
