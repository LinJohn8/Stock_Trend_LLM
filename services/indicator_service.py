from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import select

from database.db import session_scope
from database.models import StockIndicator
from services.stock_data_service import StockDataService
from utils.math_utils import clamp
from utils.stock_utils import normalize_stock_code


class IndicatorService:
    """Calculate technical indicators and simple explainable scores."""

    def calculate(self, stock_code: str) -> dict:
        code = normalize_stock_code(stock_code)
        df = StockDataService().get_daily_dataframe(code, limit=260)
        if df.empty or len(df) < 20:
            return self._empty(code)

        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        volume = df["volume"].astype(float)

        df["ma5"] = close.rolling(5).mean()
        df["ma10"] = close.rolling(10).mean()
        df["ma20"] = close.rolling(20).mean()
        df["ma60"] = close.rolling(60).mean()
        df["rsi"] = _rsi(close)
        df["macd"] = _macd(close)
        df["atr"] = _atr(high, low, close)
        df["volatility"] = close.pct_change().rolling(20).std() * np.sqrt(252)
        df["volume_ratio"] = volume / volume.rolling(20).mean()

        latest = df.iloc[-1]
        ret5 = _period_return(close, 5)
        ret20 = _period_return(close, 20)
        ret60 = _period_return(close, 60)
        max_drawdown = _max_drawdown(close.tail(60))

        trend_score = 50
        if latest["close"] > latest["ma20"]:
            trend_score += 15
        if latest["close"] > latest["ma60"]:
            trend_score += 15
        if latest["ma5"] > latest["ma20"]:
            trend_score += 10
        if ret20 < -0.08:
            trend_score -= 15
        if latest["close"] < latest["ma60"]:
            trend_score -= 15

        momentum_score = 50 + ret20 * 120 + ret60 * 60
        if latest["rsi"] > 75:
            momentum_score -= 10
        if latest["rsi"] < 30:
            momentum_score -= 5

        risk_score = 70
        if max_drawdown < -0.15:
            risk_score -= 20
        if latest["volatility"] and latest["volatility"] > 0.45:
            risk_score -= 15
        if latest["volume_ratio"] and latest["volume_ratio"] > 2 and ret5 < 0:
            risk_score -= 15

        trend_score = clamp(trend_score)
        momentum_score = clamp(momentum_score)
        risk_score = clamp(risk_score)

        summary = (
            f"收盘价 {latest['close']:.2f}，MA20 {latest['ma20']:.2f}，"
            f"近5/20/60日收益约 {ret5:.2%}/{ret20:.2%}/{ret60:.2%}，"
            f"近60日最大回撤 {max_drawdown:.2%}。"
        )
        result = {
            "stock_code": code,
            "date": latest["date"],
            "current_price": float(latest["close"]),
            "ma5": _to_float(latest["ma5"]),
            "ma10": _to_float(latest["ma10"]),
            "ma20": _to_float(latest["ma20"]),
            "ma60": _to_float(latest["ma60"]),
            "rsi": _to_float(latest["rsi"]),
            "macd": _to_float(latest["macd"]),
            "atr": _to_float(latest["atr"]),
            "volatility": _to_float(latest["volatility"]),
            "volume_ratio": _to_float(latest["volume_ratio"]),
            "ret5": ret5,
            "ret20": ret20,
            "ret60": ret60,
            "max_drawdown": max_drawdown,
            "trend_score": trend_score,
            "momentum_score": momentum_score,
            "risk_score": risk_score,
            "volatility_score": clamp(100 - (latest["volatility"] or 0) * 100),
            "technical_summary": summary,
        }
        self.save_indicator(result)
        return result

    def save_indicator(self, result: dict) -> None:
        with session_scope() as session:
            existing = session.scalar(
                select(StockIndicator).where(
                    StockIndicator.stock_code == result["stock_code"],
                    StockIndicator.date == result["date"],
                )
            )
            values = {k: result.get(k) for k in ["ma5", "ma10", "ma20", "ma60", "rsi", "macd", "atr", "volatility", "volume_ratio", "trend_score", "momentum_score", "risk_score"]}
            if existing:
                for key, value in values.items():
                    setattr(existing, key, value)
            else:
                session.add(StockIndicator(stock_code=result["stock_code"], date=result["date"], **values))

    def _empty(self, code: str) -> dict:
        return {
            "stock_code": code,
            "current_price": None,
            "trend_score": 50,
            "momentum_score": 50,
            "risk_score": 40,
            "volatility_score": 50,
            "technical_summary": "历史行情不足，技术面结论不确定。",
        }


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series) -> pd.Series:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    return (dif - dea) * 2


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _period_return(close: pd.Series, days: int) -> float:
    if len(close) <= days:
        return 0.0
    base = close.iloc[-days - 1]
    return 0.0 if base == 0 else float((close.iloc[-1] - base) / base)


def _max_drawdown(close: pd.Series) -> float:
    peak = close.cummax()
    dd = close / peak - 1
    return float(dd.min()) if not dd.empty else 0.0


def _to_float(value) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None
