from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from config.settings import get_settings


def now_tz() -> datetime:
    return datetime.now(ZoneInfo(get_settings().timezone))


def today_str() -> str:
    return now_tz().date().isoformat()


def parse_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def is_probable_cn_trading_day(day: date | None = None) -> bool:
    """Lightweight weekday check; exchange holiday calendar can be plugged in later."""
    day = day or now_tz().date()
    return day.weekday() < 5
