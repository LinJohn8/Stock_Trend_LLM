from __future__ import annotations

from sqlalchemy import delete, select

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

    def update_watchlist(
        self,
        stock_code: str,
        stock_name: str | None = None,
        industry: str | None = None,
        note: str | None = None,
        tags: str | None = None,
        is_active: bool | None = None,
    ) -> Watchlist | None:
        code = normalize_stock_code(stock_code)
        with session_scope() as session:
            item = session.scalar(select(Watchlist).where(Watchlist.stock_code == code))
            if not item:
                return None
            if stock_name is not None:
                item.stock_name = stock_name
            if industry is not None:
                item.industry = industry
            if note is not None:
                item.note = note
            if tags is not None:
                item.tags = tags
            if is_active is not None:
                item.is_active = is_active
            session.flush()
            session.refresh(item)
            return item

    def list_watchlist(self, active_only: bool = False) -> list[Watchlist]:
        with session_scope() as session:
            stmt = select(Watchlist).order_by(Watchlist.id.desc())
            if active_only:
                stmt = stmt.where(Watchlist.is_active.is_(True))
            return list(session.scalars(stmt).all())

    def deactivate_watchlist(self, stock_code: str) -> bool:
        code = normalize_stock_code(stock_code)
        with session_scope() as session:
            item = session.scalar(select(Watchlist).where(Watchlist.stock_code == code))
            if not item:
                return False
            item.is_active = False
            return True

    def delete_watchlist(self, stock_code: str) -> bool:
        code = normalize_stock_code(stock_code)
        with session_scope() as session:
            item = session.scalar(select(Watchlist).where(Watchlist.stock_code == code))
            if not item:
                return False
            session.delete(item)
            return True

    def delete_watchlist_many(self, stock_codes: list[str]) -> int:
        codes = sorted({normalize_stock_code(code) for code in stock_codes if str(code).strip()})
        if not codes:
            return 0
        with session_scope() as session:
            existing = set(session.scalars(select(Watchlist.stock_code).where(Watchlist.stock_code.in_(codes))).all())
            if not existing:
                return 0
            session.execute(delete(Watchlist).where(Watchlist.stock_code.in_(existing)))
            return len(existing)
