from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import delete, select

from database.db import session_scope
from database.models import Holding, HoldingSnapshot
from services.stock_data_service import StockDataService
from utils.math_utils import safe_pct
from utils.stock_utils import normalize_stock_code
from utils.time_utils import now_tz


@dataclass(frozen=True)
class HoldingValuation:
    current_price: float
    market_value: float
    profit_amount: float
    profit_rate: float
    max_profit_rate: float
    max_drawdown: float
    holding_days: int
    risk_level: str


class HoldingService:
    """Manage positions and daily holding snapshots."""

    def add_holding(
        self,
        stock_code: str,
        stock_name: str,
        buy_date: date,
        buy_time: time | None,
        buy_price: float,
        quantity: int,
        fee: float = 0,
        buy_reason: str = "",
        source_info: str = "",
        is_real_position: bool = True,
        note: str = "",
    ) -> Holding:
        code = normalize_stock_code(stock_code)
        total_cost = buy_price * quantity + fee
        with session_scope() as session:
            holding = Holding(
                stock_code=code,
                stock_name=stock_name,
                buy_date=buy_date,
                buy_time=buy_time,
                buy_price=buy_price,
                quantity=quantity,
                total_cost=total_cost,
                fee=fee,
                current_quantity=quantity,
                buy_reason=buy_reason,
                source_info=source_info,
                is_real_position=is_real_position,
                note=note,
                status="holding",
            )
            session.add(holding)
            session.flush()
            session.refresh(holding)
            return holding

    def update_holding(
        self,
        holding_id: int,
        stock_name: str | None = None,
        buy_date: date | None = None,
        buy_time: time | None = None,
        buy_price: float | None = None,
        quantity: int | None = None,
        fee: float | None = None,
        buy_reason: str | None = None,
        source_info: str | None = None,
        is_real_position: bool | None = None,
        note: str | None = None,
        status: str | None = None,
    ) -> Holding | None:
        with session_scope() as session:
            holding = session.get(Holding, holding_id)
            if not holding:
                return None
            if stock_name is not None:
                holding.stock_name = stock_name
            if buy_date is not None:
                holding.buy_date = buy_date
            if buy_time is not None:
                holding.buy_time = buy_time
            if buy_price is not None:
                holding.buy_price = buy_price
            if quantity is not None:
                holding.quantity = quantity
                holding.current_quantity = quantity
            if fee is not None:
                holding.fee = fee
            if quantity is not None or buy_price is not None or fee is not None:
                holding.total_cost = holding.buy_price * holding.quantity + holding.fee
            if buy_reason is not None:
                holding.buy_reason = buy_reason
            if source_info is not None:
                holding.source_info = source_info
            if is_real_position is not None:
                holding.is_real_position = is_real_position
            if note is not None:
                holding.note = note
            if status is not None:
                holding.status = status
            session.flush()
            session.refresh(holding)
            return holding

    def list_holdings(self, active_only: bool = False) -> list[Holding]:
        with session_scope() as session:
            stmt = select(Holding).order_by(Holding.id.desc())
            if active_only:
                stmt = stmt.where(Holding.status.in_(["holding", "partially_sold", "watching"]))
            return list(session.scalars(stmt).all())

    def mark_sold(self, holding_id: int) -> None:
        with session_scope() as session:
            holding = session.get(Holding, holding_id)
            if holding:
                holding.status = "sold"
                holding.current_quantity = 0

    def update_current_quantity(self, holding_id: int, current_quantity: int) -> Holding | None:
        with session_scope() as session:
            holding = session.get(Holding, holding_id)
            if not holding:
                return None
            holding.current_quantity = max(0, int(current_quantity))
            if holding.current_quantity == 0 and holding.status != "sold":
                holding.status = "sold"
            elif holding.current_quantity < holding.quantity and holding.status == "holding":
                holding.status = "partially_sold"
            session.flush()
            session.refresh(holding)
            return holding

    def delete_holding(self, holding_id: int) -> bool:
        with session_scope() as session:
            holding = session.get(Holding, holding_id)
            if not holding:
                return False
            session.execute(delete(HoldingSnapshot).where(HoldingSnapshot.holding_id == holding_id))
            session.delete(holding)
            return True

    def delete_holdings(self, holding_ids: list[int]) -> int:
        ids = sorted({int(holding_id) for holding_id in holding_ids if holding_id is not None})
        if not ids:
            return 0
        with session_scope() as session:
            existing_ids = set(session.scalars(select(Holding.id).where(Holding.id.in_(ids))).all())
            if not existing_ids:
                return 0
            session.execute(delete(HoldingSnapshot).where(HoldingSnapshot.holding_id.in_(existing_ids)))
            session.execute(delete(Holding).where(Holding.id.in_(existing_ids)))
            return len(existing_ids)

    def snapshot_holding(self, holding: Holding) -> HoldingSnapshot | None:
        valuation = self.value_holding(holding)
        if valuation is None:
            return None
        today = now_tz().date()
        with session_scope() as session:
            existing = session.scalar(
                select(HoldingSnapshot).where(
                    HoldingSnapshot.holding_id == holding.id,
                    HoldingSnapshot.date == today,
                )
            )
            if existing:
                existing.current_price = valuation.current_price
                existing.market_value = valuation.market_value
                existing.profit_amount = valuation.profit_amount
                existing.profit_rate = valuation.profit_rate
                existing.max_profit_rate = valuation.max_profit_rate
                existing.max_drawdown = valuation.max_drawdown
                existing.holding_days = valuation.holding_days
                existing.risk_level = valuation.risk_level
                snap = existing
            else:
                snap = HoldingSnapshot(
                    holding_id=holding.id,
                    stock_code=holding.stock_code,
                    date=today,
                    current_price=valuation.current_price,
                    market_value=valuation.market_value,
                    profit_amount=valuation.profit_amount,
                    profit_rate=valuation.profit_rate,
                    max_profit_rate=valuation.max_profit_rate,
                    max_drawdown=valuation.max_drawdown,
                    holding_days=valuation.holding_days,
                    benchmark_return=None,
                    industry_return=None,
                    risk_level=valuation.risk_level,
                )
                session.add(snap)
            session.flush()
            session.refresh(snap)
            return snap

    def value_holding(self, holding: Holding) -> HoldingValuation | None:
        price = StockDataService().get_latest_price(holding.stock_code)
        if price is None:
            return None
        market_value = price * holding.current_quantity
        cost_basis = holding.buy_price * holding.current_quantity + holding.fee
        profit_amount = market_value - cost_basis
        profit_rate = safe_pct(market_value, cost_basis) or 0
        holding_days = max((now_tz().date() - holding.buy_date).days, 0)

        with session_scope() as session:
            past = list(
                session.scalars(
                    select(HoldingSnapshot)
                    .where(HoldingSnapshot.holding_id == holding.id)
                    .order_by(HoldingSnapshot.date)
                )
            )
            max_profit = max([s.profit_rate for s in past] + [profit_rate])
            peak = max([s.market_value for s in past] + [market_value])
            max_drawdown = 0 if peak <= 0 else min(0, (market_value - peak) / peak)
            risk_level = "high" if profit_rate <= -0.08 or max_drawdown <= -0.15 else "medium" if profit_rate < 0 else "low"
        return HoldingValuation(
            current_price=price,
            market_value=market_value,
            profit_amount=profit_amount,
            profit_rate=profit_rate,
            max_profit_rate=max_profit,
            max_drawdown=max_drawdown,
            holding_days=holding_days,
            risk_level=risk_level,
        )

    @staticmethod
    def parse_time(value: str | None) -> time | None:
        if not value:
            return None
        return datetime.strptime(value, "%H:%M").time()
