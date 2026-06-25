from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select

from data_sources.akshare_client import AKShareClient
from database.db import session_scope
from database.models import StockDailyData, StockFundamental
from utils.logger import get_logger
from utils.stock_utils import normalize_stock_code
from utils.time_utils import now_tz

logger = get_logger("data_fetch", "data_fetch.log")


class StockDataService:
    """Fetch market data and persist it locally to reduce repeated requests."""

    def __init__(self) -> None:
        self.client = AKShareClient()

    def update_daily_data(self, stock_code: str, days: int = 420) -> int:
        code = normalize_stock_code(stock_code)
        start = date.today() - timedelta(days=days)
        df = self.client.get_daily(code, start_date=start)
        if df.empty:
            return 0
        count = 0
        with session_scope() as session:
            for row in df.to_dict("records"):
                existing = session.scalar(
                    select(StockDailyData).where(
                        StockDailyData.stock_code == code,
                        StockDailyData.date == row["date"],
                    )
                )
                values = {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume") or 0),
                    "amount": float(row.get("amount") or 0),
                    "turnover_rate": _none_or_float(row.get("turnover_rate")),
                    "pct_change": _none_or_float(row.get("pct_change")),
                }
                if existing:
                    for key, value in values.items():
                        setattr(existing, key, value)
                else:
                    session.add(StockDailyData(stock_code=code, date=row["date"], **values))
                count += 1
        logger.info("updated daily data %s rows=%s", code, count)
        return count

    def get_daily_dataframe(self, stock_code: str, limit: int = 260) -> pd.DataFrame:
        code = normalize_stock_code(stock_code)
        with session_scope() as session:
            rows = list(
                session.scalars(
                    select(StockDailyData)
                    .where(StockDailyData.stock_code == code)
                    .order_by(StockDailyData.date.desc())
                    .limit(limit)
                )
            )
        if not rows:
            self.update_daily_data(code)
            with session_scope() as session:
                rows = list(
                    session.scalars(
                        select(StockDailyData)
                        .where(StockDailyData.stock_code == code)
                        .order_by(StockDailyData.date.desc())
                        .limit(limit)
                    )
                )
        data = [
            {
                "date": r.date,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                "amount": r.amount,
                "turnover_rate": r.turnover_rate,
                "pct_change": r.pct_change,
            }
            for r in rows
        ]
        df = pd.DataFrame(data)
        if not df.empty:
            df = df.sort_values("date").reset_index(drop=True)
        return df

    def get_latest_price(self, stock_code: str) -> float | None:
        code = normalize_stock_code(stock_code)
        realtime = self.client.get_realtime(code)
        if not realtime.empty and "current_price" in realtime:
            value = _none_or_float(realtime.iloc[0].get("current_price"))
            if value and value > 0:
                return value
        df = self.get_daily_dataframe(code, limit=1)
        if not df.empty:
            return float(df.iloc[-1]["close"])
        return None

    def update_fundamentals(self, stock_code: str) -> StockFundamental:
        code = normalize_stock_code(stock_code)
        data = self.client.get_fundamentals(code)
        with session_scope() as session:
            item = StockFundamental(stock_code=code, report_date=now_tz().date(), **data)
            session.add(item)
            session.flush()
            session.refresh(item)
            return item


def _none_or_float(value) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None
