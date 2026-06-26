from __future__ import annotations

import pandas as pd

from services.stock_screening_service import ScreeningConfig, StockScreeningService


def test_screen_affordable_filters_by_one_lot_price(monkeypatch) -> None:
    service = StockScreeningService()
    market = pd.DataFrame(
        [
            {"stock_code": "000001", "stock_name": "平安银行", "current_price": 11.0, "amount": 1_000_000_000, "pct_change": 1.0},
            {"stock_code": "000560", "stock_name": "我爱我家", "current_price": 3.0, "amount": 500_000_000, "pct_change": 0.5},
            {"stock_code": "000002", "stock_name": "万科A", "current_price": 9.9, "amount": 400_000_000, "pct_change": -1.0},
        ]
    )
    monkeypatch.setattr(service.client, "get_realtime", lambda: market)
    monkeypatch.setattr(service, "_daily_enrichment", lambda code: {"score_delta": 0, "confidence_delta": 0, "reasons": [], "risks": [], "warning": ""})

    result = service.screen_affordable(ScreeningConfig(cash=1000, max_candidates=10, enrich_top=10))

    codes = {item["stock_code"] for item in result["results"]}
    assert codes == {"000560", "000002"}
    assert result["one_lot_price_limit"] == 10
    assert all(item["one_lot_cost"] <= 1000 for item in result["results"])
