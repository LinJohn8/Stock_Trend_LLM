from __future__ import annotations

from sqlalchemy import select

from database.db import session_scope
from database.models import Watchlist
from utils.stock_utils import infer_market, normalize_stock_code


class PortfolioService:
    """CRUD for watchlist stocks."""

    def add_watchlist(
        self,
        stock_code: str,
        stock_name: str = "",
        industry: str = "",
        note: str = "",
        tags: str = "",
    ) -> Watchlist:
        code = normalize_stock_code(stock_code)
        with session_scope() as session:
            item = session.scalar(select(Watchlist).where(Watchlist.stock_code == code))
            if item:
                item.stock_name = stock_name or item.stock_name
                item.industry = industry or item.industry
                item.note = note
                item.tags = tags
                item.is_active = True
            else:
                item = Watchlist(
                    stock_code=code,
                    stock_name=stock_name,
                    market=infer_market(code),
                    industry=industry,
                    note=note,
                    tags=tags,
                    is_active=True,
                )
                session.add(item)
            session.flush()
            session.refresh(item)
            return item

    def list_watchlist(self, active_only: bool = False) -> list[Watchlist]:
        with session_scope() as session:
            stmt = select(Watchlist).order_by(Watchlist.id.desc())
            if active_only:
                stmt = stmt.where(Watchlist.is_active.is_(True))
            return list(session.scalars(stmt).all())

    def deactivate_watchlist(self, stock_code: str) -> None:
        code = normalize_stock_code(stock_code)
        with session_scope() as session:
            item = session.scalar(select(Watchlist).where(Watchlist.stock_code == code))
            if item:
                item.is_active = False

    def delete_watchlist(self, stock_code: str) -> None:
        code = normalize_stock_code(stock_code)
        with session_scope() as session:
            item = session.scalar(select(Watchlist).where(Watchlist.stock_code == code))
            if item:
                session.delete(item)
