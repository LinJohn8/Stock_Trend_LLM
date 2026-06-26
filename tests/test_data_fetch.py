from __future__ import annotations

from datetime import date

from utils.stock_utils import infer_market, normalize_stock_code
from services.stock_data_service import StockDataService
from data_sources.akshare_client import AKShareClient


def test_weekly_dataframe_resample(monkeypatch) -> None:
    import pandas as pd
    from datetime import date, timedelta

    base = date(2026, 1, 1)
    df = pd.DataFrame(
        [
            {
                "date": base + timedelta(days=i),
                "open": 10 + i,
                "high": 11 + i,
                "low": 9 + i,
                "close": 10.5 + i,
                "volume": 1000 + i,
                "amount": 10000 + i,
                "turnover_rate": 1.0,
                "pct_change": 0.1,
            }
            for i in range(20)
        ]
    )
    service = StockDataService()
    monkeypatch.setattr(service, "get_daily_dataframe", lambda stock_code, limit=260: df)
    weekly = service.get_weekly_dataframe("600519", limit=10)
    assert not weekly.empty
    assert {"open", "high", "low", "close", "volume"}.issubset(weekly.columns)


def test_normalize_stock_code() -> None:
    assert normalize_stock_code("sh600519") == "600519"
    assert normalize_stock_code("000001") == "000001"


def test_infer_market() -> None:
    assert infer_market("600519") == "SH"
    assert infer_market("300750") == "SZ"


def test_tencent_realtime_fallback_parser(monkeypatch) -> None:
    class FakeResponse:
        text = 'v_sh600519="1~XD贵州茅~600519~1187.29~1184.08~1199.00~15914~7390~8515~1187.29~2~1187.28~1~1187.24~1~1187.22~2~1187.21~3~1188.00~1~1188.09~1~1188.10~6~1188.25~1~1188.40~1~~20260626100056~3.21~0.27~1199.00~1181.41~1187.29/15914/1894369603~15914~189437~0.13~17.94";'

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr("data_sources.akshare_client.requests.get", lambda *args, **kwargs: FakeResponse())
    df = AKShareClient()._get_realtime_tencent("600519")
    assert not df.empty
    assert df.iloc[0]["stock_name"] == "XD贵州茅"
    assert df.iloc[0]["current_price"] == 1187.29
    assert df.iloc[0]["amount"] == 1894370000


def test_sina_realtime_fallback_parser(monkeypatch) -> None:
    class FakeResponse:
        text = 'var hq_str_sh600519="XD贵州茅,1199.000,1184.080,1187.290,1199.000,1181.410,1187.290,1188.100,1591906,1894963477.000,700,1187.290,100,1187.280,100,1187.240,200,1187.220,300,1187.210,600,1188.100,100,1188.250,100,1188.400,100,1188.540,100,1188.800,2026-06-26,10:00:59,00,";'

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr("data_sources.akshare_client.requests.get", lambda *args, **kwargs: FakeResponse())
    df = AKShareClient()._get_realtime_sina("600519")
    assert not df.empty
    assert round(df.iloc[0]["pct_change"], 2) == 0.27


def test_yahoo_daily_fallback_parser(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "chart": {
                    "result": [
                        {
                            "timestamp": [1767225600, 1767312000],
                            "indicators": {
                                "quote": [
                                    {
                                        "open": [10, 11],
                                        "high": [12, 13],
                                        "low": [9, 10],
                                        "close": [11, 12],
                                        "volume": [1000, 1200],
                                    }
                                ],
                                "adjclose": [{"adjclose": [11, 12]}],
                            },
                        }
                    ]
                }
            }

    monkeypatch.setattr("data_sources.akshare_client.requests.get", lambda *args, **kwargs: FakeResponse())
    df = AKShareClient()._get_daily_yahoo("600519")
    assert len(df) == 2
    assert {"open", "high", "low", "close", "volume", "pct_change"}.issubset(df.columns)


def test_daily_empty_uses_yahoo_fallback(monkeypatch) -> None:
    import pandas as pd

    class FakeAk:
        def stock_zh_a_hist(self, **kwargs):
            return pd.DataFrame()

    fallback = pd.DataFrame(
        [
            {
                "stock_code": "600519",
                "date": date.today(),
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 1000,
                "amount": 0,
                "turnover_rate": None,
                "pct_change": 1.0,
            }
        ]
    )
    client = AKShareClient()
    client.ak = FakeAk()
    monkeypatch.setattr(client, "_get_daily_yahoo", lambda stock_code, start_date=None, end_date=None: fallback)
    df = client.get_daily("600519")
    assert len(df) == 1
    assert df.iloc[0]["close"] == 10.5


def test_market_snapshot_skips_update_when_cache_is_recent(monkeypatch) -> None:
    import pandas as pd
    from datetime import timedelta

    service = StockDataService()
    df = pd.DataFrame(
        [
            {
                "date": date.today() - timedelta(days=70 - i),
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10 + i / 100,
                "volume": 1000,
                "amount": 0,
                "turnover_rate": None,
                "pct_change": 0.1,
            }
            for i in range(70)
        ]
    )
    called = {"update": 0}
    monkeypatch.setattr(service, "has_recent_daily_data", lambda *args, **kwargs: True)
    monkeypatch.setattr(service, "update_daily_data", lambda *args, **kwargs: called.__setitem__("update", called["update"] + 1))
    monkeypatch.setattr(service, "resolve_stock_profile", lambda stock_code: {"stock_code": stock_code, "stock_name": "测试", "current_price": 10})
    monkeypatch.setattr(service, "get_daily_dataframe", lambda stock_code, limit=180: df.tail(limit).reset_index(drop=True))
    monkeypatch.setattr(service, "get_intraday_dataframe", lambda stock_code: pd.DataFrame())
    snapshot = service.get_market_snapshot("600519")
    assert called["update"] == 0
    assert len(snapshot["daily"]) == 70


def test_data_source_health_endpoint(monkeypatch) -> None:
    import pandas as pd
    import main

    monkeypatch.setattr(
        "main.StockDataService.get_market_snapshot",
        lambda self, stock_code, refresh=False: {
            "quote": {"stock_code": stock_code, "stock_name": "测试", "source": "unit", "current_price": 10.5},
            "daily": pd.DataFrame([{"close": 10.5}]),
            "weekly": pd.DataFrame([{"close": 10.5}]),
            "recent_5d": pd.DataFrame([{"close": 10.5}]),
            "intraday": pd.DataFrame([{"price": 10.5}]),
        },
    )
    result = main.data_source_health("600519")
    assert result["quote_source"] == "unit"
    assert result["daily_rows"] == 1


def test_update_fundamentals_is_idempotent(monkeypatch) -> None:
    from database.db import init_db

    init_db()
    service = StockDataService()
    monkeypatch.setattr(
        service.client,
        "get_fundamentals",
        lambda stock_code: {
            "pe": 20.0,
            "pb": 3.0,
            "roe": None,
            "revenue_growth": None,
            "profit_growth": None,
            "gross_margin": None,
            "debt_ratio": None,
            "cash_flow": None,
        },
    )
    first = service.update_fundamentals("600519")
    second = service.update_fundamentals("600519")
    assert first.id == second.id
    assert second.pe == 20.0


def test_tencent_intraday_fallback_parser(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": {
                    "sh600519": {
                        "data": {
                            "data": [
                                "0930 1199.00 969 116183100.00",
                                "0931 1193.85 2240 268166759.81",
                            ]
                        }
                    }
                }
            }

    monkeypatch.setattr("data_sources.akshare_client.requests.get", lambda *args, **kwargs: FakeResponse())
    df = AKShareClient()._get_intraday_tencent("600519")
    assert len(df) == 2
    assert df.iloc[0]["price"] == 1199.0
    assert df.iloc[1]["amount"] == 268166759.81
