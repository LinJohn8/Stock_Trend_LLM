from __future__ import annotations

import pandas as pd

from services.indicator_service import _max_drawdown, _period_return


def test_period_return() -> None:
    close = pd.Series([10, 11, 12, 13, 14, 15])
    assert round(_period_return(close, 5), 4) == 0.5


def test_max_drawdown() -> None:
    close = pd.Series([10, 12, 9, 11])
    assert round(_max_drawdown(close), 4) == -0.25
