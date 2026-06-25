from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from utils.logger import get_logger
from utils.stock_utils import normalize_stock_code

logger = get_logger("data_fetch", "data_fetch.log")


class AKShareClient:
    """Defensive wrapper around AKShare A-share endpoints."""

    def __init__(self) -> None:
        try:
            import akshare as ak  # type: ignore
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.error("AKShare import failed: %s", exc)
            ak = None
        self.ak = ak

    def _require_ak(self) -> Any:
        if self.ak is None:
            raise RuntimeError("AKShare 未安装或导入失败")
        return self.ak

    def get_daily(
        self,
        stock_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """Fetch A-share daily bars from Eastmoney via AKShare."""
        code = normalize_stock_code(stock_code)
        start = (start_date or (date.today() - timedelta(days=420))).strftime("%Y%m%d")
        end = (end_date or date.today()).strftime("%Y%m%d")
        try:
            ak = self._require_ak()
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start,
                end_date=end,
                adjust=adjust,
            )
            if df is None or df.empty:
                logger.warning("empty daily data: %s", code)
                return pd.DataFrame()
            mapping = {
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
                "振幅": "amplitude",
                "涨跌幅": "pct_change",
                "涨跌额": "change_amount",
                "换手率": "turnover_rate",
            }
            df = df.rename(columns=mapping)
            df["stock_code"] = code
            df["date"] = pd.to_datetime(df["date"]).dt.date
            for col in ["open", "high", "low", "close", "volume", "amount", "turnover_rate", "pct_change"]:
                if col in df:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df[["stock_code", "date", "open", "high", "low", "close", "volume", "amount", "turnover_rate", "pct_change"]]
        except Exception as exc:
            logger.exception("fetch daily failed %s: %s", code, exc)
            return pd.DataFrame()

    def get_realtime(self, stock_code: str | None = None) -> pd.DataFrame:
        """Fetch realtime spot data. Passing a code filters the full market table."""
        try:
            ak = self._require_ak()
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return pd.DataFrame()
            mapping = {
                "代码": "stock_code",
                "名称": "stock_name",
                "最新价": "current_price",
                "涨跌幅": "pct_change",
                "涨跌额": "change_amount",
                "成交量": "volume",
                "成交额": "amount",
                "振幅": "amplitude",
                "最高": "high",
                "最低": "low",
                "今开": "open",
                "昨收": "prev_close",
                "量比": "volume_ratio",
                "换手率": "turnover_rate",
                "市盈率-动态": "pe",
                "市净率": "pb",
            }
            df = df.rename(columns=mapping)
            if "stock_code" in df:
                df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)
            if stock_code:
                code = normalize_stock_code(stock_code)
                df = df[df["stock_code"] == code]
            return df
        except Exception as exc:
            logger.exception("fetch realtime failed: %s", exc)
            return pd.DataFrame()

    def get_index_daily(self, index_code: str = "sh000300") -> pd.DataFrame:
        """Fetch index daily bars; common codes include sh000001 and sh000300."""
        try:
            ak = self._require_ak()
            df = ak.stock_zh_index_daily(symbol=index_code)
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.rename(columns={"date": "date", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"})
            df["date"] = pd.to_datetime(df["date"]).dt.date
            return df
        except Exception as exc:
            logger.exception("fetch index failed %s: %s", index_code, exc)
            return pd.DataFrame()

    def get_fundamentals(self, stock_code: str) -> dict[str, float | None]:
        """Best-effort fundamentals from realtime valuation columns and optional APIs."""
        code = normalize_stock_code(stock_code)
        result: dict[str, float | None] = {
            "pe": None,
            "pb": None,
            "roe": None,
            "revenue_growth": None,
            "profit_growth": None,
            "gross_margin": None,
            "debt_ratio": None,
            "cash_flow": None,
        }
        try:
            spot = self.get_realtime(code)
            if not spot.empty:
                row = spot.iloc[0]
                result["pe"] = _to_float(row.get("pe"))
                result["pb"] = _to_float(row.get("pb"))
        except Exception as exc:
            logger.warning("fundamental realtime fallback failed %s: %s", code, exc)
        return result

    def get_industry_board(self) -> pd.DataFrame:
        try:
            ak = self._require_ak()
            df = ak.stock_board_industry_name_em()
            return df if df is not None else pd.DataFrame()
        except Exception as exc:
            logger.exception("fetch industry board failed: %s", exc)
            return pd.DataFrame()


def _to_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None
