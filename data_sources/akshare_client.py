from __future__ import annotations

from datetime import date, timedelta
from math import ceil
from typing import Any

import pandas as pd
import requests

from utils.logger import get_logger
from utils.stock_utils import exchange_prefixed_code, infer_market, normalize_stock_code

logger = get_logger("data_fetch", "data_fetch.log")

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 StockTrendLLM/0.1",
    "Referer": "https://finance.sina.com.cn/",
}

_MARKET_CACHE: dict[str, Any] = {"time": None, "df": pd.DataFrame()}
_MARKET_CACHE_SECONDS = 180


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
                logger.info("empty daily data from akshare %s, using yahoo fallback", code)
                return self._get_daily_yahoo(code, start_date, end_date)
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
            logger.info("fetch daily failed %s, using yahoo fallback: %s", code, exc)
            return self._get_daily_yahoo(code, start_date, end_date)

    def get_realtime(self, stock_code: str | None = None) -> pd.DataFrame:
        """Fetch realtime spot data. Passing a code filters the full market table."""
        if stock_code:
            direct = self._get_realtime_fallback(normalize_stock_code(stock_code))
            if not direct.empty:
                return direct
        try:
            ak = self._require_ak()
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return self._get_realtime_eastmoney_market()
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
            logger.info("fetch realtime failed, using fallback: %s", exc)
            if stock_code:
                return self._get_realtime_fallback(normalize_stock_code(stock_code))
            market = self._get_realtime_eastmoney_market()
            if not market.empty:
                return market
            return self._get_realtime_sina_market()

    def get_stock_name(self, stock_code: str) -> str:
        code = normalize_stock_code(stock_code)
        try:
            ak = self._require_ak()
            for attr in ["stock_info_a_code_name", "stock_info_sh_name_code", "stock_info_sz_name_code", "stock_info_bj_name_code"]:
                if not hasattr(ak, attr):
                    continue
                df = getattr(ak, attr)()
                if df is None or df.empty:
                    continue
                code_col = next((col for col in df.columns if "代码" in str(col) or "code" in str(col).lower()), None)
                name_col = next((col for col in df.columns if "名称" in str(col) or "name" in str(col).lower()), None)
                if not code_col or not name_col:
                    continue
                hit = df[df[code_col].astype(str).str.zfill(6) == code]
                if not hit.empty:
                    return str(hit.iloc[0][name_col])
        except Exception as exc:
            logger.warning("lookup stock name failed %s: %s", code, exc)
        fallback = self._get_realtime_fallback(code)
        if not fallback.empty:
            return str(fallback.iloc[0].get("stock_name") or "")
        return ""

    def get_intraday(self, stock_code: str) -> pd.DataFrame:
        """Fetch intraday minute bars when AKShare exposes them for the code."""
        code = normalize_stock_code(stock_code)
        direct = self._get_intraday_tencent(code)
        if not direct.empty:
            return direct
        try:
            ak = self._require_ak()
            if hasattr(ak, "stock_intraday_em"):
                df = ak.stock_intraday_em(symbol=code)
            elif hasattr(ak, "stock_zh_a_hist_min_em"):
                df = ak.stock_zh_a_hist_min_em(symbol=code, period="1", adjust="")
            else:
                return pd.DataFrame()
            if df is None or df.empty:
                return pd.DataFrame()
            mapping = {
                "时间": "time",
                "日期时间": "time",
                "最新价": "price",
                "成交价": "price",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
                "均价": "avg_price",
            }
            df = df.rename(columns=mapping)
            if "time" not in df.columns:
                for col in df.columns:
                    if "时间" in str(col) or "date" in str(col).lower():
                        df = df.rename(columns={col: "time"})
                        break
            if "price" not in df.columns and "close" in df.columns:
                df["price"] = df["close"]
            for col in ["price", "open", "high", "low", "close", "volume", "amount", "avg_price"]:
                if col in df:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            keep = [col for col in ["time", "price", "open", "high", "low", "close", "volume", "amount", "avg_price"] if col in df.columns]
            return df[keep].dropna(subset=["price"]) if "price" in keep else pd.DataFrame()
        except Exception as exc:
            logger.warning("fetch intraday failed %s, using fallback: %s", code, exc)
            return self._get_intraday_sina(code)

    def get_daily_technical_summary(self, stock_code: str) -> dict[str, Any]:
        df = self.get_daily(stock_code)
        if df.empty:
            return {"stock_code": normalize_stock_code(stock_code), "available": False}
        return {
            "stock_code": normalize_stock_code(stock_code),
            "available": True,
            "first_date": df["date"].min(),
            "last_date": df["date"].max(),
            "rows": len(df),
            "latest_close": float(df.iloc[-1]["close"]),
            "latest_volume": float(df.iloc[-1]["volume"]),
        }

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
            logger.warning("fetch index failed %s: %s", index_code, exc)
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
            logger.warning("fetch industry board failed: %s", exc)
            return pd.DataFrame()

    def _get_realtime_fallback(self, stock_code: str) -> pd.DataFrame:
        for fetcher in (self._get_realtime_tencent, self._get_realtime_sina, self._get_realtime_eastmoney_direct):
            df = fetcher(stock_code)
            if not df.empty:
                return df
        return pd.DataFrame()

    def _get_realtime_tencent(self, stock_code: str) -> pd.DataFrame:
        symbol = exchange_prefixed_code(stock_code)
        try:
            response = requests.get(f"https://qt.gtimg.cn/q={symbol}", timeout=10, headers=REQUEST_HEADERS)
            response.raise_for_status()
            text = response.text
            if '="' not in text:
                return pd.DataFrame()
            values = text.split('="', 1)[1].rsplit('"', 1)[0].split("~")
            if len(values) < 39:
                return pd.DataFrame()
            row = {
                "stock_code": stock_code,
                "stock_name": values[1],
                "current_price": _to_float(values[3]),
                "pct_change": _to_float(values[32]),
                "change_amount": _to_float(values[31]),
                "open": _to_float(values[5]),
                "high": _to_float(values[33]),
                "low": _to_float(values[34]),
                "prev_close": _to_float(values[4]),
                "volume": _to_float(values[36]),
                "amount": None if _to_float(values[37]) is None else _to_float(values[37]) * 10000,
                "volume_ratio": None,
                "turnover_rate": _to_float(values[38]),
                "pe": _to_float(values[39]) if len(values) > 39 else None,
                "pb": None,
                "source": "tencent_realtime",
            }
            return pd.DataFrame([row])
        except Exception as exc:
            logger.warning("tencent realtime fallback failed %s: %s", stock_code, exc)
            return pd.DataFrame()

    def _get_realtime_sina(self, stock_code: str) -> pd.DataFrame:
        symbol = exchange_prefixed_code(stock_code)
        try:
            response = requests.get(f"https://hq.sinajs.cn/list={symbol}", timeout=10, headers=REQUEST_HEADERS)
            response.raise_for_status()
            text = response.text
            if '="' not in text:
                return pd.DataFrame()
            values = text.split('="', 1)[1].rsplit('"', 1)[0].split(",")
            if len(values) < 32 or not values[0]:
                return pd.DataFrame()
            current = _to_float(values[3])
            prev = _to_float(values[2])
            change = None if current is None or prev in (None, 0) else current - prev
            pct = None if change is None or not prev else change / prev * 100
            row = {
                "stock_code": stock_code,
                "stock_name": values[0],
                "current_price": current,
                "pct_change": pct,
                "change_amount": change,
                "open": _to_float(values[1]),
                "high": _to_float(values[4]),
                "low": _to_float(values[5]),
                "prev_close": prev,
                "volume": _to_float(values[8]),
                "amount": _to_float(values[9]),
                "volume_ratio": None,
                "turnover_rate": None,
                "pe": None,
                "pb": None,
                "source": "sina_realtime",
            }
            return pd.DataFrame([row])
        except Exception as exc:
            logger.warning("sina realtime fallback failed %s: %s", stock_code, exc)
            return pd.DataFrame()

    def _get_realtime_eastmoney_direct(self, stock_code: str) -> pd.DataFrame:
        market = infer_market(stock_code)
        secid_prefix = {"SH": "1", "SZ": "0", "BJ": "0"}.get(market, "1")
        url = (
            "https://push2.eastmoney.com/api/qt/stock/get"
            f"?secid={secid_prefix}.{stock_code}"
            "&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f107,f162,f167,f168,f169,f170"
        )
        try:
            response = requests.get(url, timeout=10, headers=REQUEST_HEADERS)
            response.raise_for_status()
            data = (response.json() or {}).get("data") or {}
            if not data:
                return pd.DataFrame()
            current = _em_price(data.get("f43"))
            prev = _em_price(data.get("f60"))
            row = {
                "stock_code": stock_code,
                "stock_name": data.get("f58") or "",
                "current_price": current,
                "pct_change": _em_percent(data.get("f170")),
                "change_amount": _em_price(data.get("f169")),
                "open": _em_price(data.get("f46")),
                "high": _em_price(data.get("f44")),
                "low": _em_price(data.get("f45")),
                "prev_close": prev,
                "volume": _to_float(data.get("f47")),
                "amount": _to_float(data.get("f48")),
                "volume_ratio": None,
                "turnover_rate": _em_percent(data.get("f168")),
                "pe": _em_percent(data.get("f162")),
                "pb": None,
                "source": "eastmoney_direct_realtime",
            }
            return pd.DataFrame([row])
        except Exception as exc:
            logger.warning("eastmoney direct realtime fallback failed %s: %s", stock_code, exc)
            return pd.DataFrame()

    def _get_realtime_eastmoney_market(self) -> pd.DataFrame:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": 5000,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
            "fields": "f2,f3,f4,f5,f6,f8,f9,f10,f12,f14,f15,f16,f17,f18,f23",
        }
        try:
            response = requests.get(url, params=params, timeout=12, headers=REQUEST_HEADERS)
            response.raise_for_status()
            rows = ((response.json() or {}).get("data") or {}).get("diff") or []
            parsed = []
            for item in rows:
                code = str(item.get("f12") or "").zfill(6)
                if len(code) != 6:
                    continue
                parsed.append(
                    {
                        "stock_code": code,
                        "stock_name": item.get("f14") or "",
                        "current_price": _to_float(item.get("f2")),
                        "pct_change": _to_float(item.get("f3")),
                        "change_amount": _to_float(item.get("f4")),
                        "volume": _to_float(item.get("f5")),
                        "amount": _to_float(item.get("f6")),
                        "turnover_rate": _to_float(item.get("f8")),
                        "pe": _to_float(item.get("f9")),
                        "volume_ratio": _to_float(item.get("f10")),
                        "high": _to_float(item.get("f15")),
                        "low": _to_float(item.get("f16")),
                        "open": _to_float(item.get("f17")),
                        "prev_close": _to_float(item.get("f18")),
                        "pb": _to_float(item.get("f23")),
                        "source": "eastmoney_market_realtime",
                    }
                )
            return pd.DataFrame(parsed)
        except Exception as exc:
            logger.info("eastmoney market realtime fallback failed: %s", exc)
            return pd.DataFrame()

    def _get_realtime_sina_market(self) -> pd.DataFrame:
        cached_at = _MARKET_CACHE.get("time")
        cached_df = _MARKET_CACHE.get("df")
        if cached_at is not None and isinstance(cached_df, pd.DataFrame) and not cached_df.empty:
            if (pd.Timestamp.now() - cached_at).total_seconds() <= _MARKET_CACHE_SECONDS:
                return cached_df.copy()
        count_url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeStockCount"
        data_url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
        try:
            count_resp = requests.get(count_url, params={"node": "hs_a"}, timeout=10, headers=REQUEST_HEADERS)
            count_resp.raise_for_status()
            count = int(str(count_resp.text).strip().strip('"') or "0")
            rows = []
            page_size = 100
            for page in range(1, max(1, ceil(count / page_size)) + 1):
                params = {
                    "page": page,
                    "num": page_size,
                    "sort": "amount",
                    "asc": 0,
                    "node": "hs_a",
                    "symbol": "",
                    "_s_r_a": "page",
                }
                response = requests.get(data_url, params=params, timeout=12, headers=REQUEST_HEADERS)
                response.raise_for_status()
                page_rows = response.json() or []
                if not page_rows:
                    break
                rows.extend(page_rows)
            parsed = []
            for item in rows:
                code = str(item.get("code") or "").zfill(6)
                if len(code) != 6:
                    continue
                parsed.append(
                    {
                        "stock_code": code,
                        "stock_name": item.get("name") or "",
                        "current_price": _to_float(item.get("trade")),
                        "pct_change": _to_float(item.get("changepercent")),
                        "change_amount": _to_float(item.get("pricechange")),
                        "open": _to_float(item.get("open")),
                        "high": _to_float(item.get("high")),
                        "low": _to_float(item.get("low")),
                        "prev_close": _to_float(item.get("settlement")),
                        "volume": _to_float(item.get("volume")),
                        "amount": _to_float(item.get("amount")),
                        "turnover_rate": _to_float(item.get("turnoverratio")),
                        "pe": _to_float(item.get("per")),
                        "pb": _to_float(item.get("pb")),
                        "volume_ratio": None,
                        "source": "sina_market_realtime",
                    }
                )
            df = pd.DataFrame(parsed)
            if not df.empty:
                _MARKET_CACHE["time"] = pd.Timestamp.now()
                _MARKET_CACHE["df"] = df.copy()
            return df
        except Exception as exc:
            logger.warning("sina market realtime fallback failed: %s", exc)
            return pd.DataFrame()

    def _get_daily_yahoo(self, stock_code: str, start_date: date | None = None, end_date: date | None = None) -> pd.DataFrame:
        suffix = ".SS" if infer_market(stock_code) == "SH" else ".SZ"
        period1 = int(pd.Timestamp(start_date or (date.today() - timedelta(days=420))).timestamp())
        period2 = int((pd.Timestamp(end_date or date.today()) + pd.Timedelta(days=1)).timestamp())
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{stock_code}{suffix}"
        params = {"period1": period1, "period2": period2, "interval": "1d", "events": "history"}
        try:
            response = requests.get(url, params=params, timeout=12, headers=REQUEST_HEADERS)
            response.raise_for_status()
            result = (((response.json() or {}).get("chart") or {}).get("result") or [None])[0]
            if not result:
                return pd.DataFrame()
            timestamps = result.get("timestamp") or []
            quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
            adjclose = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
            rows = []
            for idx, ts in enumerate(timestamps):
                close = _list_get(quote.get("close"), idx)
                if close is None:
                    continue
                rows.append(
                    {
                        "stock_code": stock_code,
                        "date": pd.to_datetime(ts, unit="s").date(),
                        "open": _list_get(quote.get("open"), idx),
                        "high": _list_get(quote.get("high"), idx),
                        "low": _list_get(quote.get("low"), idx),
                        "close": close,
                        "volume": _list_get(quote.get("volume"), idx) or 0,
                        "amount": 0,
                        "turnover_rate": None,
                        "pct_change": None,
                        "adjclose": _list_get(adjclose, idx),
                    }
                )
            df = pd.DataFrame(rows)
            if not df.empty:
                for col in ["open", "high", "low", "close", "volume", "amount", "turnover_rate", "pct_change"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df["pct_change"] = df["close"].pct_change() * 100
                df["source"] = "yahoo_daily"
            return df[["stock_code", "date", "open", "high", "low", "close", "volume", "amount", "turnover_rate", "pct_change"]]
        except Exception as exc:
            logger.warning("yahoo daily fallback failed %s: %s", stock_code, exc)
            return pd.DataFrame()

    def _get_intraday_sina(self, stock_code: str) -> pd.DataFrame:
        # Sina's quote endpoint provides the latest tick; use it as a minimal real fallback
        # so the UI can still render a current-price point when minute history is unavailable.
        realtime = self._get_realtime_sina(stock_code)
        if realtime.empty:
            realtime = self._get_realtime_tencent(stock_code)
        if realtime.empty:
            return pd.DataFrame()
        row = realtime.iloc[0]
        return pd.DataFrame(
            [
                {
                    "time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "price": row.get("current_price"),
                    "volume": row.get("volume"),
                    "amount": row.get("amount"),
                }
            ]
        ).dropna(subset=["price"])

    def _get_intraday_tencent(self, stock_code: str) -> pd.DataFrame:
        symbol = exchange_prefixed_code(stock_code)
        url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={symbol}"
        try:
            response = requests.get(url, timeout=10, headers=REQUEST_HEADERS)
            response.raise_for_status()
            payload = response.json()
            rows = ((((payload or {}).get("data") or {}).get(symbol) or {}).get("data") or {}).get("data") or []
            parsed = []
            today = pd.Timestamp.now().strftime("%Y-%m-%d")
            for row in rows:
                parts = str(row).split()
                if len(parts) < 2:
                    continue
                minute = parts[0]
                parsed.append(
                    {
                        "time": f"{today} {minute[:2]}:{minute[2:]}:00",
                        "price": _to_float(parts[1]),
                        "volume": _to_float(parts[2]) if len(parts) > 2 else None,
                        "amount": _to_float(parts[3]) if len(parts) > 3 else None,
                    }
                )
            df = pd.DataFrame(parsed)
            return df.dropna(subset=["price"]) if not df.empty else pd.DataFrame()
        except Exception as exc:
            logger.warning("tencent intraday fallback failed %s: %s", stock_code, exc)
            return pd.DataFrame()


def _to_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _em_price(value: Any) -> float | None:
    number = _to_float(value)
    if number is None:
        return None
    return number / 100


def _em_percent(value: Any) -> float | None:
    number = _to_float(value)
    if number is None:
        return None
    return number / 100


def _list_get(values: list | None, index: int) -> Any:
    if not values or index >= len(values):
        return None
    return values[index]
