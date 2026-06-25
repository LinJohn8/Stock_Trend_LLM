from __future__ import annotations

from data_sources.announcement_client import AnnouncementClient
from data_sources.news_client import NewsClient


RISK_KEYWORDS = ["减持", "亏损", "监管", "问询函", "立案", "处罚", "退市", "ST", "诉讼", "商誉减值", "业绩预告下修", "解禁", "大额质押"]
POSITIVE_KEYWORDS = ["增持", "回购", "中标", "业绩增长", "合同", "政策支持", "新产品", "扩产", "分红"]


class SentimentService:
    def analyze(self, stock_code: str) -> dict:
        news = NewsClient().get_stock_news(stock_code)
        announcements = AnnouncementClient().get_announcements(stock_code)
        titles = [x.get("title", "") for x in news + announcements]
        text = " ".join(titles)
        risk_hits = [kw for kw in RISK_KEYWORDS if kw in text]
        good_hits = [kw for kw in POSITIVE_KEYWORDS if kw in text]
        score = 50 + len(good_hits) * 8 - len(risk_hits) * 12
        score = max(0, min(100, score))
        level = "high" if risk_hits else "medium" if not titles else "low"
        if not titles:
            summary = "第一版新闻/公告接口为占位或暂无数据，消息面维持中性并提示不确定。"
        else:
            summary = f"公告/新闻 {len(titles)} 条，利好关键词 {good_hits or '无'}，风险关键词 {risk_hits or '无'}。"
        return {
            "news_score": score,
            "news_risk_level": level,
            "news_summary": summary,
            "risk_keywords": risk_hits,
            "positive_keywords": good_hits,
            "titles": titles,
        }
