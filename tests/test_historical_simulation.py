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
