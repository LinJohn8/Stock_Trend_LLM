from __future__ import annotations

from datetime import datetime

from services.news_reliability_service import NewsReliabilityService


def test_news_reliability_scores_keyword_and_risk() -> None:
    service = NewsReliabilityService()
    item = {
        "source": "eastmoney_stock_news",
        "title": "600519 贵州茅台 发布回购与分红计划",
        "content": "公司公告增持与分红。",
        "url": "https://example.com/a",
        "published_at": datetime.utcnow(),
    }
    score = service.score(item, "600519", "贵州茅台")
    assert score["relevance_score"] > 40
    assert "600519" in score["matched_keywords"]
    assert score["positive_keywords"]


def test_news_reliability_hash_stable() -> None:
    service = NewsReliabilityService()
    item = {"title": "A", "url": "https://example.com", "content": "B"}
    assert service.content_hash(item) == service.content_hash(item)
