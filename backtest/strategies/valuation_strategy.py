from __future__ import annotations


def valuation_score(pe: float | None, pb: float | None) -> float:
    score = 50
    if pe and 0 < pe < 30:
        score += 20
    if pb and 0 < pb < 4:
        score += 10
    if pe and pe > 80:
        score -= 15
    return max(0, min(100, score))
