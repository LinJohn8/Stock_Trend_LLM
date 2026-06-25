from __future__ import annotations


def ma_signal(close: float, ma20: float | None, ma60: float | None) -> str:
    if ma20 and ma60 and close > ma20 > ma60:
        return "watch"
    if ma60 and close < ma60:
        return "avoid"
    return "uncertain"
