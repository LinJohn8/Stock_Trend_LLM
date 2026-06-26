from __future__ import annotations

from datetime import datetime

from data_sources.announcement_client import AnnouncementClient
from data_sources.news_client import NewsClient
from services.news_reliability_service import NewsReliabilityService


def test_eastmoney_notice_api_fallback(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "result": {
                    "data": [
                        {
                            "TITLE": "贵州茅台关于分红的公告",
                            "INFO_CODE": "AN202601010001",
                            "NOTICE_DATE": "2026-01-01 18:00:00",
                            "COLUMNS": "分红融资",
                        }
                    ]
                }
            }

    def fake_get(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr("data_sources.announcement_client.requests.get", fake_get)
    items = AnnouncementClient()._eastmoney_notice_api("600519", limit=5)
    assert items[0]["source"] == "eastmoney_notice_api"
    assert "分红" in items[0]["title"]
    assert items[0]["published_at"].year == 2026


def test_news_client_source_summary() -> None:
    items = [{"source": "a"}, {"source": "a"}, {"source": "b"}, {}]
    assert NewsClient().source_summary(items) == {"a": 2, "b": 1, "unknown": 1}


def test_news_client_builds_multi_topic_queries() -> None:
    queries = NewsClient().build_intelligence_queries(
        "600519",
        "贵州茅台",
        extra_keywords=["飞天批价"],
        industry="白酒 消费",
        topic_scope=["stock", "industry", "market_sentiment", "supply_chain"],
    )
    joined = " ".join(queries)
    assert "贵州茅台" in joined
    assert "白酒 消费 行业" in joined
    assert "北向资金 A股" in joined
    assert "贵州茅台 竞品" in joined
    assert "飞天批价" in joined


def test_news_client_caps_expanded_queries(monkeypatch) -> None:
    client = NewsClient()
    called = []
    monkeypatch.setattr(client, "get_akshare_stock_news", lambda *args, **kwargs: [])
    monkeypatch.setattr("data_sources.news_client.AnnouncementClient.get_announcements", lambda *args, **kwargs: [])

    def fake_search(query: str, limit: int = 30):
        called.append(query)
        return [{"source": "rss", "title": query, "url": query, "published_at": None, "content": query, "summary": query, "raw": {}}]

    monkeypatch.setattr(client, "search_rss", fake_search)
    items = client.get_stock_news(
        "600519",
        "贵州茅台",
        limit=80,
        extra_keywords=[f"关键词{i}" for i in range(20)],
        industry="白酒 消费",
    )
    assert len(called) <= 18
    assert len(items) <= 80


def test_announcement_source_scores_higher_than_unknown() -> None:
    service = NewsReliabilityService()
    base = {
        "title": "600519 贵州茅台 发布分红公告",
        "content": "公司公告分红，现金分红比例为 50%。",
        "url": "https://example.com/a",
        "published_at": datetime.utcnow(),
    }
    official = service.score({**base, "source": "eastmoney_notice_api"}, "600519", "贵州茅台")
    unknown = service.score({**base, "source": "unknown"}, "600519", "贵州茅台")
    assert official["source_credibility"] > unknown["source_credibility"]
    assert official["reliability_score"] > unknown["reliability_score"]
    assert official["quality_label"] in {"high_confidence", "usable"}
