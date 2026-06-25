from __future__ import annotations


def win_rate(values: list[float]) -> float:
    return 0.0 if not values else sum(1 for v in values if v > 0) / len(values)


def average_return(values: list[float]) -> float:
    return 0.0 if not values else sum(values) / len(values)
