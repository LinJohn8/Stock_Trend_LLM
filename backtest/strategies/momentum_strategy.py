from __future__ import annotations


def momentum_signal(ret20: float, risk_level: str) -> str:
    if risk_level == "high":
        return "avoid"
    if 0.03 <= ret20 <= 0.20:
        return "watch"
    if ret20 > 0.30:
        return "uncertain"
    return "uncertain"
