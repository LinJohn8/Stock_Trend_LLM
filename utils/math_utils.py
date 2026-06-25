from __future__ import annotations

import math


def clamp(value: float, lower: float = 0, upper: float = 100) -> float:
    if value is None or math.isnan(float(value)):
        return lower
    return max(lower, min(upper, float(value)))


def safe_pct(current: float | None, base: float | None) -> float | None:
    if current is None or base in (None, 0):
        return None
    return (current - base) / base


def format_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"
