from __future__ import annotations

import pandas as pd
import pytest

from dashboard.simulation_view import _flatten_local_rise_projection


def test_flatten_local_rise_projection_keeps_dates_and_flattens_drops() -> None:
    df = pd.DataFrame(
        [
            {"date": "2026-01-01", "actual_close": 10.0, "simulated_close": 8.0},
            {"date": "2026-01-02", "actual_close": 11.0, "simulated_close": 8.4},
            {"date": "2026-01-03", "actual_close": 10.5, "simulated_close": 8.2},
            {"date": "2026-01-04", "actual_close": 10.8, "simulated_close": 8.3},
        ]
    )

    result = _flatten_local_rise_projection(df)

    assert list(result["date"]) == list(df["date"])
    assert list(result["simulated_flat_rise"]) == pytest.approx([8.0, 8.4, 8.4, 8.5])
    assert list(result["is_rise"]) == ["否", "是", "否", "是"]
    assert result["simulated_flat_rise"].is_monotonic_increasing
