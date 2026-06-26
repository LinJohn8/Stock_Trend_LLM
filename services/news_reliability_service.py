from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime
from typing import Any

from services.sentiment_keywords import POSITIVE_KEYWORDS, RISK_KEYWORDS
from utils.math_utils import clamp

SOURCE_CREDIBILITY = {
    "eastmoney_announcement": 86,
    "eastmoney_notice_api": 84,
    "eastmoney_stock_news": 78,
    "google_news_cn": 62,
    "google_news_finance": 64,
    "rsshub": 58,
    "unknown": 45,
}


class NewsReliabilityService:
    """Score stock-news evidence before it is passed to an LLM."""

    def content_hash(self, item: dict[str, Any]) -> str:
        basis = (item.get("url") or "") + "\n" + (item.get("title") or "") + "\n" + (item.get("content") or "")
        return hashlib.sha256(basis.encode("utf-8", errors="ignore")).hexdigest()

    def score(self, item: dict[str, Any], stock_code: str, stock_name: str, extra_keywords: list[str] | None = None) -> dict[str, Any]:
        text = _clean_text(" ".join([str(item.get("title") or ""), str(item.get("summary") or ""), str(item.get("content") or "")]))
        keywords = [kw for kw in [stock_code, stock_name, *(extra_keywords or [])] if kw]
        matched = [kw for kw in keywords if kw.lower() in text.lower()]
        keyword_score = min(100, len(matched) * 35)
        semantic_score = self._semantic_overlap(text, keywords)
        source_score = SOURCE_CREDIBILITY.get(str(item.get("source") or "unknown"), SOURCE_CREDIBILITY["unknown"])
        recency_score = self._recency_score(item.get("published_at"))
        risk_hits = [kw for kw in RISK_KEYWORDS if kw in text]
        positive_hits = [kw for kw in POSITIVE_KEYWORDS if kw in text]
        event_types = _event_types(text)
        entities = _extract_entities(text)
        sentiment_score = clamp(50 + len(positive_hits) * 9 - len(risk_hits) * 13)
        event_bonus = 8 if event_types else 0
        relevance_score = clamp(keyword_score * 0.50 + semantic_score * 0.32 + recency_score * 0.10 + event_bonus)
        reliability_score = clamp(source_score * 0.45 + relevance_score * 0.35 + recency_score * 0.20)
        return {
            "source_credibility": source_score,
            "relevance_score": relevance_score,
            "keyword_score": keyword_score,
            "semantic_score": semantic_score,
            "reliability_score": reliability_score,
            "sentiment_score": sentiment_score,
            "matched_keywords": matched,
            "risk_keywords": risk_hits,
            "positive_keywords": positive_hits,
            "event_types": event_types,
            "extracted_entities": entities,
            "quality_label": _quality_label(reliability_score, relevance_score, risk_hits),
            "evidence_reason": f"来源可信度 {source_score:.0f}，关键词命中 {matched or '无'}，语义近似 {semantic_score:.0f}，时效 {recency_score:.0f}。",
        }

    def _semantic_overlap(self, text: str, keywords: list[str]) -> float:
        text_tokens = set(_tokens(text))
        keyword_tokens = set()
        for keyword in keywords:
            keyword_tokens.update(_tokens(keyword))
        if not text_tokens or not keyword_tokens:
            return 0
        return clamp(len(text_tokens & keyword_tokens) / max(1, len(keyword_tokens)) * 100)

    def _recency_score(self, published_at) -> float:
        if not published_at:
            return 45
        if isinstance(published_at, str):
            try:
                published_at = datetime.fromisoformat(published_at)
            except Exception:
                return 45
        hours = max(0, (datetime.utcnow() - published_at).total_seconds() / 3600)
        return clamp(100 * math.exp(-hours / 96), lower=20, upper=100)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]{2,}", text.lower()) + re.findall(r"[\u4e00-\u9fff]{2,}", text)


def _clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _event_types(text: str) -> list[str]:
    mapping = {
        "earnings": ["业绩", "财报", "净利润", "营收", "亏损", "预告"],
        "regulatory": ["监管", "问询函", "立案", "处罚", "退市"],
        "capital_action": ["回购", "增持", "减持", "分红", "解禁", "质押"],
        "business_contract": ["中标", "合同", "订单", "合作"],
        "policy_industry": ["政策", "补贴", "行业", "扩产", "产能"],
        "litigation": ["诉讼", "仲裁", "纠纷"],
    }
    return [event for event, keywords in mapping.items() if any(keyword in text for keyword in keywords)]


def _extract_entities(text: str) -> dict[str, list[str]]:
    money = re.findall(r"\d+(?:\.\d+)?\s*(?:亿元|万元|元)", text)
    percentages = re.findall(r"\d+(?:\.\d+)?\s*%", text)
    dates = re.findall(r"\d{4}年\d{1,2}月\d{1,2}日|\d{4}-\d{1,2}-\d{1,2}", text)
    shares = re.findall(r"\d+(?:\.\d+)?\s*(?:万股|亿股|股)", text)
    return {
        "money": money[:8],
        "percentages": percentages[:8],
        "dates": dates[:8],
        "shares": shares[:8],
    }


def _quality_label(reliability_score: float, relevance_score: float, risk_hits: list[str]) -> str:
    if reliability_score >= 72 and relevance_score >= 55:
        return "high_confidence_risk" if risk_hits else "high_confidence"
    if reliability_score >= 55 and relevance_score >= 35:
        return "usable"
    if reliability_score >= 42:
        return "needs_cross_check"
    return "weak"
