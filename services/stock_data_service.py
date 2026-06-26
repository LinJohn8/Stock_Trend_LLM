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

    def get_quote(self, stock_code: str) -> dict:
        code = normalize_stock_code(stock_code)
        realtime = self.client.get_realtime(code)
        if not realtime.empty:
            row = realtime.iloc[0]
            return {
                "stock_code": code,
                "stock_name": str(row.get("stock_name") or ""),
                "current_price": _none_or_float(row.get("current_price")),
                "pct_change": _none_or_float(row.get("pct_change")),
                "change_amount": _none_or_float(row.get("change_amount")),
                "open": _none_or_float(row.get("open")),
                "high": _none_or_float(row.get("high")),
                "low": _none_or_float(row.get("low")),
                "prev_close": _none_or_float(row.get("prev_close")),
                "volume": _none_or_float(row.get("volume")),
                "amount": _none_or_float(row.get("amount")),
                "volume_ratio": _none_or_float(row.get("volume_ratio")),
                "turnover_rate": _none_or_float(row.get("turnover_rate")),
                "pe": _none_or_float(row.get("pe")),
                "pb": _none_or_float(row.get("pb")),
                "source": str(row.get("source") or "akshare_realtime"),
            }
        df = self.get_daily_dataframe(code, limit=2)
        if df.empty:
            return {"stock_code": code, "stock_name": "", "current_price": None}
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else None
        current = float(latest["close"])
        prev_close = None if prev is None else float(prev["close"])
        pct_change = None if not prev_close else (current - prev_close) / prev_close * 100
        return {
            "stock_code": code,
            "stock_name": "",
            "current_price": current,
            "pct_change": pct_change,
            "change_amount": None if prev_close is None else current - prev_close,
            "open": float(latest["open"]),
            "high": float(latest["high"]),
            "low": float(latest["low"]),
            "prev_close": prev_close,
            "volume": float(latest["volume"]),
            "amount": float(latest["amount"]),
            "volume_ratio": None,
            "turnover_rate": _none_or_float(latest.get("turnover_rate")),
            "pe": None,
            "pb": None,
            "source": "local_daily_fallback",
        }

    def resolve_stock_profile(self, stock_code: str) -> dict:
        code = normalize_stock_code(stock_code)
        quote = self.get_quote(code)
        if not quote.get("stock_name"):
            quote["stock_name"] = self.client.get_stock_name(code)
        quote["market"] = "SH" if code.startswith("6") else "SZ" if code.startswith(("0", "3")) else "BJ" if code.startswith(("4", "8")) else "CN"
        quote["display_name"] = f"{quote['stock_code']} {quote.get('stock_name') or '名称待获取'}"
        return quote

    def get_weekly_dataframe(self, stock_code: str, limit: int = 120) -> pd.DataFrame:
        df = self.get_daily_dataframe(stock_code, limit=max(limit * 7, 260))
        if df.empty:
            return df
        weekly = (
            df.assign(date=pd.to_datetime(df["date"]))
            .set_index("date")
            .resample("W-FRI")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                    "amount": "sum",
                    "turnover_rate": "mean",
                    "pct_change": "sum",
                }
            )
            .dropna(subset=["open", "high", "low", "close"])
            .tail(limit)
            .reset_index()
        )
        weekly["date"] = weekly["date"].dt.date
        return weekly

    def get_recent_days_dataframe(self, stock_code: str, days: int = 5) -> pd.DataFrame:
        return self.get_daily_dataframe(stock_code, limit=max(days, 5)).tail(days).reset_index(drop=True)

    def get_intraday_dataframe(self, stock_code: str) -> pd.DataFrame:
        return self.client.get_intraday(stock_code)

    def get_market_snapshot(
        self,
        stock_code: str,
        daily_limit: int = 180,
        include_industry: bool = False,
        refresh: bool = False,
    ) -> dict:
        code = normalize_stock_code(stock_code)
        if refresh or not self.has_recent_daily_data(code, min_rows=min(60, daily_limit)):
            self.update_daily_data(code)
        quote = self.resolve_stock_profile(code)
        daily = self.get_daily_dataframe(code, limit=daily_limit)
        weekly = self.get_weekly_dataframe(code, limit=80)
        intraday = self.get_intraday_dataframe(code)
        industry = self.client.get_industry_board() if include_industry else pd.DataFrame()
        return {
            "quote": quote,
            "daily": daily,
            "weekly": weekly,
            "recent_5d": self.get_recent_days_dataframe(code, days=5),
            "intraday": intraday,
            "technical_summary": self._daily_summary(code, daily),
            "industry_board": industry,
        }

    def has_recent_daily_data(self, stock_code: str, min_rows: int = 60, max_age_days: int = 5) -> bool:
        code = normalize_stock_code(stock_code)
        with session_scope() as session:
            rows = list(
                session.scalars(
                    select(StockDailyData)
                    .where(StockDailyData.stock_code == code)
                    .order_by(StockDailyData.date.desc())
                    .limit(min_rows)
                )
            )
        if len(rows) < min_rows:
            return False
        latest = rows[0].date
        return (date.today() - latest).days <= max_age_days

    def _daily_summary(self, stock_code: str, df: pd.DataFrame) -> dict[str, Any]:
        code = normalize_stock_code(stock_code)
        if df.empty:
            return {"stock_code": code, "available": False}
        return {
            "stock_code": code,
            "available": True,
            "first_date": df["date"].min(),
            "last_date": df["date"].max(),
            "rows": len(df),
            "latest_close": float(df.iloc[-1]["close"]),
            "latest_volume": float(df.iloc[-1]["volume"]),
            "source": "local_daily_cache",
        }

    def get_stock_context(self, stock_code: str) -> dict[str, Any]:
        code = normalize_stock_code(stock_code)
        snapshot = self.get_market_snapshot(code)
        from services.indicator_service import IndicatorService
        from services.fundamental_service import FundamentalService
        from services.sentiment_service import SentimentService

        technical = IndicatorService().calculate(code)
        fundamental = FundamentalService().analyze(code)
        sentiment = SentimentService().analyze(code)
        return {
            "quote": snapshot["quote"],
            "daily": snapshot["daily"],
            "weekly": snapshot["weekly"],
            "recent_5d": snapshot["recent_5d"],
            "intraday": snapshot["intraday"],
            "technical": technical,
            "fundamental": fundamental,
            "sentiment": sentiment,
            "technical_summary": snapshot["technical_summary"],
            "industry_board": snapshot["industry_board"],
        }

    def update_fundamentals(self, stock_code: str) -> StockFundamental:
        code = normalize_stock_code(stock_code)
        data = self.client.get_fundamentals(code)
        report_date = now_tz().date()
        with session_scope() as session:
            item = session.scalar(
                select(StockFundamental).where(
                    StockFundamental.stock_code == code,
                    StockFundamental.report_date == report_date,
                )
            )
            if item:
                for key, value in data.items():
                    setattr(item, key, value)
            else:
                item = StockFundamental(stock_code=code, report_date=report_date, **data)
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
