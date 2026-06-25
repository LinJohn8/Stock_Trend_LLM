from __future__ import annotations

from utils.stock_utils import infer_market, normalize_stock_code


def test_normalize_stock_code() -> None:
    assert normalize_stock_code("sh600519") == "600519"
    assert normalize_stock_code("000001") == "000001"


def test_infer_market() -> None:
    assert infer_market("600519") == "SH"
    assert infer_market("300750") == "SZ"
