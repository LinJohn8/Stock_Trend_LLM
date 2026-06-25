from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import select

from database.db import session_scope
from database.models import Holding, HoldingSnapshot
from services.stock_data_service import StockDataService
from utils.math_utils import safe_pct
from utils.stock_utils import normalize_stock_code
from utils.time_utils import now_tz


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

    def delete_holding(self, holding_id: int) -> None:
        with session_scope() as session:
            holding = session.get(Holding, holding_id)
            if holding:
                session.delete(holding)

    def snapshot_holding(self, holding: Holding) -> HoldingSnapshot | None:
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
            snap = HoldingSnapshot(
                holding_id=holding.id,
                stock_code=holding.stock_code,
                date=now_tz().date(),
                current_price=price,
                market_value=market_value,
                profit_amount=profit_amount,
                profit_rate=profit_rate,
                max_profit_rate=max_profit,
                max_drawdown=max_drawdown,
                holding_days=holding_days,
                benchmark_return=None,
                industry_return=None,
                risk_level=risk_level,
            )
            session.add(snap)
            session.flush()
            session.refresh(snap)
            return snap

    @staticmethod
    def parse_time(value: str | None) -> time | None:
        if not value:
            return None
        return datetime.strptime(value, "%H:%M").time()
