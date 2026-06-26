from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from data_sources.news_client import NewsClient
from database.db import session_scope
from database.models import NewsArticle, StockNewsEvidence
from services.news_reliability_service import NewsReliabilityService
from utils.stock_utils import normalize_stock_code


class NewsIngestionService:
    """Collect, de-duplicate, score and persist stock-related news evidence."""

    def __init__(self) -> None:
        self.client = NewsClient()
        self.scorer = NewsReliabilityService()

    def collect_for_stock(
        self,
        stock_code: str,
        stock_name: str = "",
        extra_keywords: list[str] | None = None,
        limit: int = 30,
        industry: str = "",
        topic_scope: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        code = normalize_stock_code(stock_code)
        raw_items = self.client.get_stock_news(
            code,
            stock_name,
            limit=limit,
            extra_keywords=extra_keywords,
            industry=industry,
            topic_scope=topic_scope,
        )
        saved: list[dict[str, Any]] = []
        with session_scope() as session:
            for item in raw_items:
                if not item.get("title"):
                    continue
                content_hash = self.scorer.content_hash(item)
                scored = self.scorer.score(item, code, stock_name, extra_keywords)
                if scored["relevance_score"] < 18:
                    continue
                article = session.scalar(select(NewsArticle).where(NewsArticle.content_hash == content_hash))
                if not article:
                    article = NewsArticle(
                        source=str(item.get("source") or "unknown"),
                        title=str(item.get("title") or ""),
                        url=str(item.get("url") or ""),
                        published_at=item.get("published_at"),
                        content=str(item.get("content") or ""),
                        summary=str(item.get("summary") or ""),
                        raw_json=json.dumps(item.get("raw") or {}, ensure_ascii=False, default=str),
                        content_hash=content_hash,
                        source_credibility=scored["source_credibility"],
                    )
                    session.add(article)
                    session.flush()
                evidence = session.scalar(
                    select(StockNewsEvidence).where(
                        StockNewsEvidence.stock_code == code,
                        StockNewsEvidence.article_id == article.id,
                    )
                )
                values = {
                    "stock_name": stock_name,
                    "relevance_score": scored["relevance_score"],
                    "keyword_score": scored["keyword_score"],
                    "semantic_score": scored["semantic_score"],
                    "reliability_score": scored["reliability_score"],
                    "sentiment_score": scored["sentiment_score"],
                    "matched_keywords": json.dumps(scored["matched_keywords"], ensure_ascii=False),
                    "risk_keywords": json.dumps(scored["risk_keywords"], ensure_ascii=False),
                    "positive_keywords": json.dumps(scored["positive_keywords"], ensure_ascii=False),
                    "event_types": json.dumps(scored["event_types"], ensure_ascii=False),
                    "extracted_entities": json.dumps(scored["extracted_entities"], ensure_ascii=False),
                    "evidence_reason": scored["evidence_reason"],
                }
                if evidence:
                    for key, value in values.items():
                        setattr(evidence, key, value)
                else:
                    evidence = StockNewsEvidence(stock_code=code, article_id=article.id, **values)
                    session.add(evidence)
                    session.flush()
                saved.append(self._to_dict(article, evidence))
        return saved

    def get_evidence(self, stock_code: str, limit: int = 20) -> list[dict[str, Any]]:
        code = normalize_stock_code(stock_code)
        with session_scope() as session:
            rows = list(
                session.execute(
                    select(NewsArticle, StockNewsEvidence)
                    .join(StockNewsEvidence, StockNewsEvidence.article_id == NewsArticle.id)
                    .where(StockNewsEvidence.stock_code == code)
                    .order_by(StockNewsEvidence.reliability_score.desc(), NewsArticle.published_at.desc().nullslast())
                    .limit(limit)
                ).all()
            )
            return [self._to_dict(article, evidence) for article, evidence in rows]

    def _to_dict(self, article: NewsArticle, evidence: StockNewsEvidence) -> dict[str, Any]:
        return {
            "article_id": article.id,
            "source": article.source,
            "title": article.title,
            "url": article.url,
            "published_at": article.published_at,
            "summary": article.summary or article.content[:240],
            "source_credibility": article.source_credibility,
            "relevance_score": evidence.relevance_score,
            "keyword_score": evidence.keyword_score,
            "semantic_score": evidence.semantic_score,
            "reliability_score": evidence.reliability_score,
            "sentiment_score": evidence.sentiment_score,
            "matched_keywords": json.loads(evidence.matched_keywords or "[]"),
            "risk_keywords": json.loads(evidence.risk_keywords or "[]"),
            "positive_keywords": json.loads(evidence.positive_keywords or "[]"),
            "event_types": json.loads(getattr(evidence, "event_types", "[]") or "[]"),
            "extracted_entities": json.loads(getattr(evidence, "extracted_entities", "{}") or "{}"),
            "evidence_reason": evidence.evidence_reason,
        }
