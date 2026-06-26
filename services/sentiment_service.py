from __future__ import annotations

from data_sources.announcement_client import AnnouncementClient
from services.news_ingestion_service import NewsIngestionService
from services.sentiment_keywords import POSITIVE_KEYWORDS, RISK_KEYWORDS


class SentimentService:
    def analyze(self, stock_code: str) -> dict:
        evidence = NewsIngestionService().get_evidence(stock_code, limit=12)
        announcements = AnnouncementClient().get_announcements(stock_code)
        titles = [item.get("title", "") for item in evidence] + [x.get("title", "") for x in announcements]
        text = " ".join(titles)
        risk_hits = sorted({kw for item in evidence for kw in item.get("risk_keywords", [])} | {kw for kw in RISK_KEYWORDS if kw in text})
        good_hits = sorted({kw for item in evidence for kw in item.get("positive_keywords", [])} | {kw for kw in POSITIVE_KEYWORDS if kw in text})
        event_types = sorted({event for item in evidence for event in item.get("event_types", [])})
        score = 50 + len(good_hits) * 8 - len(risk_hits) * 12
        if {"regulatory", "litigation"} & set(event_types):
            score -= 10
        if "business_contract" in event_types:
            score += 5
        if evidence:
            weighted = sum(item["sentiment_score"] * item["reliability_score"] for item in evidence)
            total = sum(item["reliability_score"] for item in evidence) or 1
            score = (score + weighted / total) / 2
        score = max(0, min(100, score))
        level = "high" if risk_hits else "medium" if not titles else "low"
        if not titles:
            summary = "暂无已入库的可靠新闻证据，消息面维持中性并提示不确定。"
        else:
            avg_reliability = sum(item.get("reliability_score", 0) for item in evidence) / max(1, len(evidence))
            summary = f"新闻证据 {len(evidence)} 条，平均可靠度 {avg_reliability:.1f}，事件类型 {event_types or '无'}，利好关键词 {good_hits or '无'}，风险关键词 {risk_hits or '无'}。"
        return {
            "news_score": score,
            "news_risk_level": level,
            "news_summary": summary,
            "risk_keywords": risk_hits,
            "positive_keywords": good_hits,
            "event_types": event_types,
            "titles": titles,
            "evidence": evidence[:8],
        }
