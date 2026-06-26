from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote_plus, urlencode

import pandas as pd
import requests

from utils.logger import get_logger
from utils.stock_utils import normalize_stock_code

logger = get_logger("data_fetch", "data_fetch.log")


class AnnouncementClient:
    """Best-effort announcement fetcher with defensive fallbacks."""

    def get_announcements(self, stock_code: str, limit: int = 20) -> list[dict[str, Any]]:
        code = normalize_stock_code(stock_code)
        items: list[dict[str, Any]] = []
        items.extend(self._eastmoney_announcements(code, limit=limit))
        if len(items) < limit:
            items.extend(self._eastmoney_notice_api(code, limit=limit))
        return _dedupe(items)[:limit]

    def _eastmoney_announcements(self, stock_code: str, limit: int = 20) -> list[dict[str, Any]]:
        try:
            import akshare as ak  # type: ignore

            if not hasattr(ak, "stock_notice_report_em"):
                return []
            df = ak.stock_notice_report_em(symbol=stock_code)
            if df is None or df.empty:
                return []
            items = []
            for row in df.head(limit).to_dict("records"):
                title = str(row.get("公告标题") or row.get("title") or "")
                url = str(row.get("公告链接") or row.get("url") or "")
                published = row.get("公告时间") or row.get("date") or row.get("time")
                items.append(
                    {
                        "source": "eastmoney_announcement",
                        "title": title,
                        "url": url,
                        "published_at": _parse_datetime(published),
                        "summary": title,
                        "content": title,
                        "raw": row,
                    }
                )
            return items
        except Exception as exc:
            logger.warning("announcement fetch failed %s: %s", stock_code, exc)
            return []

    def _eastmoney_notice_api(self, stock_code: str, limit: int = 20) -> list[dict[str, Any]]:
        market = "SH" if stock_code.startswith("6") else "SZ" if stock_code.startswith(("0", "3")) else "BJ"
        secid = f"{market}{stock_code}"
        params = {
            "type": "RPT_LICO_FN_CPD",
            "sty": "ALL",
            "source": "WEB",
            "client": "WEB",
            "pageSize": limit,
            "pageNumber": 1,
            "filter": f'(SECURITY_CODE="{stock_code}")',
        }
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get?" + urlencode(params)
        try:
            response = requests.get(
                url,
                timeout=12,
                headers={
                    "User-Agent": "Mozilla/5.0 StockTrendLLM/0.1",
                    "Referer": f"https://data.eastmoney.com/notices/stock/{secid}.html",
                },
            )
            response.raise_for_status()
            payload = response.json()
            rows = (((payload or {}).get("result") or {}).get("data") or [])[:limit]
            items = []
            for row in rows:
                title = str(row.get("TITLE") or row.get("NOTICE_TITLE") or "")
                info_code = row.get("INFO_CODE") or row.get("ART_CODE") or ""
                url = row.get("URL") or _notice_url(str(info_code))
                published = row.get("NOTICE_DATE") or row.get("REPORT_DATE") or row.get("EITIME")
                notice_type = str(row.get("COLUMNS") or row.get("ANN_RELCOLUMNS") or "")
                items.append(
                    {
                        "source": "eastmoney_notice_api",
                        "title": title,
                        "url": url,
                        "published_at": _parse_datetime(published),
                        "summary": "；".join([x for x in [title, notice_type] if x]),
                        "content": "；".join([x for x in [title, notice_type] if x]),
                        "raw": row,
                    }
                )
            return items
        except Exception as exc:
            logger.warning("eastmoney notice api failed %s: %s", stock_code, exc)
            return []

    def search_keyword(self, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        try:
            import akshare as ak  # type: ignore

            if not hasattr(ak, "stock_notice_report_em"):
                return []
            df = ak.stock_notice_report_em(symbol=quote_plus(keyword))
            if df is None or df.empty:
                return []
            return df.head(limit).to_dict("records")
        except Exception as exc:
            logger.warning("announcement keyword fetch failed %s: %s", keyword, exc)
            return []


def _parse_datetime(value: Any):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return pd.to_datetime(value).to_pydatetime().replace(tzinfo=None)
    except Exception:
        return None


def _notice_url(info_code: str) -> str:
    if not info_code:
        return ""
    return f"https://data.eastmoney.com/notices/detail/{info_code}.html"


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in items:
        key = (item.get("url") or "") + "|" + (item.get("title") or "")
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output
