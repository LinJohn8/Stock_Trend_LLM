from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
from functools import lru_cache
from collections import Counter
from typing import Any
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET
import re

import requests

from data_sources.announcement_client import AnnouncementClient
from utils.logger import get_logger
from utils.stock_utils import normalize_stock_code

logger = get_logger("data_fetch", "data_fetch.log")

DEFAULT_RSS_SOURCES = {
    "google_news_cn": "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
    "google_news_finance": "https://news.google.com/rss/search?q={query}%20A股%20股票&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
}

INTELLIGENCE_TOPICS = {
    "stock": ["{stock_name}", "{stock_code}", "{stock_name} 股价", "{stock_name} 财报"],
    "announcement": ["{stock_name} 公告", "{stock_name} 分红 回购 减持 增持", "{stock_code} 业绩预告"],
    "industry": ["{industry} 行业", "{industry} 政策", "{industry} 景气度"],
    "macro_policy": ["A股 政策", "证监会 A股", "央行 利率 A股", "人民币 汇率 A股"],
    "market_sentiment": ["沪深300 资金流向", "北向资金 A股", "融资融券 A股", "市场情绪 A股"],
    "supply_chain": ["{stock_name} 上游", "{stock_name} 下游", "{stock_name} 竞品", "{stock_name} 渠道"],
}


class NewsClient:
    """Multi-source news fetcher with defensive fallbacks."""

    def get_stock_news(
        self,
        stock_code: str,
        stock_name: str = "",
        limit: int = 30,
        extra_keywords: list[str] | None = None,
        industry: str = "",
        topic_scope: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        code = normalize_stock_code(stock_code)
        queries = self.build_intelligence_queries(code, stock_name, extra_keywords, industry, topic_scope)[:18]
        items: list[dict[str, Any]] = []
        items.extend(self.get_akshare_stock_news(code, stock_name, limit=limit))
        items.extend(AnnouncementClient().get_announcements(code, limit=limit))
        per_query_limit = max(4, min(12, limit // max(1, len(queries)) + 2))
        for query in queries:
            items.extend(self.search_rss(query, limit=per_query_limit))
        items = _dedupe_items(items)
        return items[:limit]

    def source_summary(self, items: list[dict[str, Any]]) -> dict[str, int]:
        return dict(Counter(str(item.get("source") or "unknown") for item in items))

    def build_intelligence_queries(
        self,
        stock_code: str,
        stock_name: str = "",
        extra_keywords: list[str] | None = None,
        industry: str = "",
        topic_scope: list[str] | None = None,
    ) -> list[str]:
        scope = topic_scope or ["stock", "announcement", "industry", "macro_policy", "market_sentiment", "supply_chain"]
        context = {
            "stock_code": stock_code,
            "stock_name": stock_name or stock_code,
            "industry": industry or stock_name or "A股",
        }
        queries: list[str] = []
        for topic in scope:
            for template in INTELLIGENCE_TOPICS.get(topic, []):
                query = template.format(**context).strip()
                if query and "  " not in query:
                    queries.append(query)
        for keyword in extra_keywords or []:
            if keyword.strip():
                queries.append(keyword.strip())
                queries.append(f"{stock_name or stock_code} {keyword.strip()}")
        queries.append(" ".join([x for x in [stock_name, stock_code, "A股 股票 公告"] if x]))
        return _dedupe_text(queries)

    @lru_cache(maxsize=64)
    def search_rss(self, query: str, limit: int = 30) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for source, template in DEFAULT_RSS_SOURCES.items():
            url = template.format(query=quote_plus(query))
            try:
                response = requests.get(url, timeout=12, headers={"User-Agent": "StockTrendLLM/0.1"})
                response.raise_for_status()
                items.extend(self._parse_rss(source, response.text, limit=limit))
            except Exception as exc:
                logger.info("rss fetch failed source=%s, continuing with other sources: %s", source, exc)
        return _dedupe_items(items)[:limit]

    @lru_cache(maxsize=128)
    def get_akshare_stock_news(self, stock_code: str, stock_name: str = "", limit: int = 20) -> list[dict[str, Any]]:
        try:
            import akshare as ak  # type: ignore

            if not hasattr(ak, "stock_news_em"):
                return []
            df = ak.stock_news_em(symbol=stock_code)
            if df is None or df.empty:
                return []
            items = []
            for row in df.head(limit).to_dict("records"):
                title = str(row.get("新闻标题") or row.get("title") or "")
                url = str(row.get("新闻链接") or row.get("url") or "")
                content = str(row.get("新闻内容") or row.get("content") or "")
                published = row.get("发布时间") or row.get("date") or row.get("time")
                items.append(
                    {
                        "source": "eastmoney_stock_news",
                        "title": title,
                        "url": url,
                        "published_at": _parse_datetime(published),
                        "content": content,
                        "summary": content[:240],
                        "raw": row,
                    }
                )
            return _dedupe_items(items)
        except Exception as exc:
            logger.info("akshare stock news failed %s %s, using RSS fallback: %s", stock_code, stock_name, exc)
            return self.search_rss(" ".join([x for x in [stock_name, stock_code, "股票"] if x]), limit=limit)

    def _parse_rss(self, source: str, xml_text: str, limit: int) -> list[dict[str, Any]]:
        root = ET.fromstring(xml_text)
        nodes = root.findall(".//item") or root.findall("{http://www.w3.org/2005/Atom}entry")
        items = []
        for node in nodes[:limit]:
            title = _node_text(node, "title")
            link = _node_text(node, "link")
            if not link:
                link_node = node.find("{http://www.w3.org/2005/Atom}link")
                link = "" if link_node is None else link_node.attrib.get("href", "")
            published = _node_text(node, "pubDate") or _node_text(node, "published") or _node_text(node, "updated")
            summary = _node_text(node, "description") or _node_text(node, "summary")
            clean_summary = _clean_html(summary)
            items.append(
                {
                    "source": source,
                    "title": title,
                    "url": link,
                    "published_at": _parse_datetime(published),
                    "content": clean_summary,
                    "summary": clean_summary[:240],
                    "raw": {"source": source, "published": published},
                }
            )
        return items


def _node_text(node: ET.Element, tag: str) -> str:
    found = node.find(tag)
    if found is None:
        found = node.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
    return "" if found is None or found.text is None else found.text.strip()


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value)
    for parser in (
        lambda x: parsedate_to_datetime(x).replace(tzinfo=None),
        lambda x: datetime.fromisoformat(x.replace("Z", "+00:00")).replace(tzinfo=None),
    ):
        try:
            return parser(text)
        except Exception:
            pass
    return None


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = _dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _dedupe_key(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "").lower()
    title = re.sub(r"\s+", "", title)
    title = re.sub(r"[-_｜|].*$", "", title)
    url = str(item.get("url") or "")
    if "news.google.com/rss/articles/" in url:
        return title or url
    return (url or title)[:300]


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()
