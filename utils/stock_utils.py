from __future__ import annotations

import re


ASHARE_RE = re.compile(r"^(?:sh|sz|bj)?(?P<code>\d{6})$", re.IGNORECASE)


def normalize_stock_code(stock_code: str) -> str:
    match = ASHARE_RE.match(str(stock_code).strip())
    if not match:
        raise ValueError(f"无效 A 股代码: {stock_code}")
    return match.group("code")


def infer_market(stock_code: str) -> str:
    code = normalize_stock_code(stock_code)
    if code.startswith("6"):
        return "SH"
    if code.startswith(("0", "3")):
        return "SZ"
    if code.startswith(("4", "8")):
        return "BJ"
    return "CN"


def exchange_prefixed_code(stock_code: str) -> str:
    code = normalize_stock_code(stock_code)
    market = infer_market(code)
    prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(market, "")
    return f"{prefix}{code}"


def is_st_stock(stock_name: str | None) -> bool:
    return bool(stock_name and ("ST" in stock_name.upper() or "退" in stock_name))
