from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from services.algorithm_service import AnalysisAlgorithm
from services.historical_simulation_service import SimulationConfig
from services.historical_simulation_service import HistoricalSimulationService


def test_target_fraction_modes() -> None:
    service = HistoricalSimulationService()
    decision = {"action": "buy_candidate", "overall_score": 75}
    assert service._target_fraction(decision, "conservative", 0.85) == 0.45
    assert service._target_fraction(decision, "aggressive", 0.85) == 0.75
    assert service._target_fraction(decision, "consensus", 0.85) == 0.60


def test_low_cash_records_trade_blocker(monkeypatch) -> None:
    service = HistoricalSimulationService()
    start = date.today() - timedelta(days=70)
    rows = []
    for idx in range(65):
        rows.append(
            {
                "date": start + timedelta(days=idx),
                "open": 3.0 + idx * 0.01,
                "high": 3.1 + idx * 0.01,
                "low": 2.9 + idx * 0.01,
                "close": 3.0 + idx * 0.01,
                "volume": 1_000_000,
                "amount": 3_000_000,
                "turnover_rate": 1.0,
                "pct_change": 0.1,
            }
        )
    df = pd.DataFrame(rows)
    monkeypatch.setattr(service, "_load_stock_data", lambda *args, **kwargs: df)
    monkeypatch.setattr(service, "_benchmark_curve", lambda *args, **kwargs: [0 for _ in args[-1]])
    monkeypatch.setattr(service, "save", lambda output: None)
    service.algorithm_service.list_algorithms = lambda: [
        AnalysisAlgorithm(
            "always_buy",
            "测试买入",
            "always buy",
            1.0,
            lambda ctx: {"score": 80, "view": "test", "direction": "bullish", "position_bias": 0.3, "reasons": ["测试买入"], "risks": []},
            "测试",
            True,
            "core",
        )
    ]
    service.algorithm_service.default_algorithm_ids = lambda: ["always_buy"]

    result = service.run(SimulationConfig(stock_code="000560", initial_cash=100))

    assert result["trades"] == []
    assert result["diagnostics"]["trade_blockers"]
    assert "不足" in result["diagnostics"]["trade_blockers"][0]["message"] or "低于一手成本" in result["diagnostics"]["trade_blockers"][0]["message"]


def test_technical_snapshot_has_generated_algorithm_inputs() -> None:
    service = HistoricalSimulationService()
    start = date.today() - timedelta(days=280)
    df = pd.DataFrame(
        [
            {
                "date": start + timedelta(days=idx),
                "open": 10 + idx * 0.02,
                "high": 10.2 + idx * 0.02,
                "low": 9.8 + idx * 0.02,
                "close": 10 + idx * 0.02,
                "volume": 1_000_000 + idx * 1000,
                "amount": 10_000_000,
                "turnover_rate": 1.0,
                "pct_change": 0.1,
            }
            for idx in range(260)
        ]
    )

    snapshot = service._technical_snapshot("000560", df)

    for key in ["ma10", "ma30", "ma90", "ma120", "ma250", "ret10", "ret30", "ret90", "ret120", "rsi", "macd", "atr", "volatility"]:
        assert key in snapshot
    assert snapshot["ma250"] is not None
    assert snapshot["volatility"] is not None


def test_simulation_outputs_price_projection(monkeypatch) -> None:
    service = HistoricalSimulationService()
    start = date.today() - timedelta(days=100)
    df = pd.DataFrame(
        [
            {
                "date": start + timedelta(days=idx),
                "open": 8 + idx * 0.03,
                "high": 8.2 + idx * 0.03,
                "low": 7.8 + idx * 0.03,
                "close": 8 + idx * 0.03,
                "volume": 2_000_000,
                "amount": 16_000_000,
                "turnover_rate": 1.2,
                "pct_change": 0.2,
            }
            for idx in range(90)
        ]
    )
    monkeypatch.setattr(service, "_load_stock_data", lambda *args, **kwargs: df)
    monkeypatch.setattr(service, "_benchmark_curve", lambda *args, **kwargs: [0 for _ in args[-1]])
    monkeypatch.setattr(service, "save", lambda output: None)

    result = service.run(SimulationConfig(stock_code="000560", initial_cash=10000))

    assert result["price_projection"]
    assert len(result["price_projection"]) == len(result["equity_curve"])
    assert result["summary"]["projection_error"]["available"] is True
    assert not any(item.get("errors", 0) for item in result["diagnostics"]["algorithms"].values())
