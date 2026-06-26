from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.ui import apply_chart_interaction, badge, inject_global_style, render_copy_button, render_hero, render_insight, render_kpi_grid, render_link_card, render_query_ribbon, render_static_table
from data_sources.news_client import NewsClient
from database.db import init_db
from services.news_ingestion_service import NewsIngestionService
from services.sentiment_service import SentimentService

st.set_page_config(page_title="新闻情报", layout="wide")
init_db()
inject_global_style()
service = NewsIngestionService()
news_client = NewsClient()

TOPIC_OPTIONS = {
    "stock": "个股本身",
    "announcement": "公告事项",
    "industry": "行业景气/政策",
    "macro_policy": "宏观政策",
    "market_sentiment": "市场资金/情绪",
    "supply_chain": "竞品/上下游",
}


def _quality_text(item: dict) -> str:
    reliability = float(item.get("reliability_score") or 0)
    relevance = float(item.get("relevance_score") or 0)
    if reliability >= 72 and relevance >= 55:
        return "高可信"
    if reliability >= 55 and relevance >= 35:
        return "可用"
    if reliability >= 42:
        return "需交叉验证"
    return "弱证据"


def _quality_tone(item: dict) -> str:
    label = _quality_text(item)
    if label == "高可信":
        return "buy"
    if label == "可用":
        return "neutral"
    if label == "需交叉验证":
        return "watch"
    return "risk"


def _news_copy_text(items: list[dict] | list) -> str:
    if hasattr(items, "to_dict"):
        items = items.to_dict("records")
    if not items:
        return "暂无新闻证据。"
    lines = ["# 新闻证据分析"]
    for idx, item in enumerate(items[:50], start=1):
        lines.extend(
            [
                f"{idx}. {item.get('标题') or item.get('title') or '-'}",
                f"   来源：{item.get('来源') or item.get('source') or '-'} | 质量：{item.get('质量') or '-'} | 可靠度：{item.get('可靠度') or item.get('reliability_score') or '-'} | 相关性：{item.get('相关性') or item.get('relevance_score') or '-'}",
                f"   事件：{item.get('事件') or item.get('event_types') or '-'}",
                f"   风险词：{item.get('风险词') or item.get('risk_keywords') or '-'}",
                f"   链接：{item.get('链接') or item.get('url') or '-'}",
            ]
        )
    return "\n".join(lines)


render_hero(
    "新闻情报证据舱",
    "从个股、公告、行业、政策、资金情绪和上下游多个角度生成查询，再进行去重、相关性、来源可信度、事件类型和实体提取评分。",
    "Evidence Intelligence",
    [("多主题检索", "neutral"), ("可靠度过滤", "buy"), ("风险优先", "watch")],
)

with st.form("news_collect"):
    c1, c2, c3 = st.columns([1, 1, 1])
    stock_code = c1.text_input("股票代码", value="600519")
    stock_name = c2.text_input("股票名称", value="贵州茅台")
    industry = c3.text_input("行业/主题", value="白酒 消费")
    topic_labels = st.multiselect(
        "情报范围",
        list(TOPIC_OPTIONS.keys()),
        default=["stock", "announcement", "industry", "market_sentiment"],
        format_func=lambda key: TOPIC_OPTIONS[key],
        help="不是只搜股票名，而是扩展到公告、行业、政策、市场资金和上下游，从更多角度收集证据。",
    )
    extra = st.text_input("额外关键词，用逗号分隔", value="")
    limit = st.slider("最多保存证据", 20, 120, 60, step=10, help="值越大覆盖面越广，但抓取时间也会更长。")
    preview_queries = news_client.build_intelligence_queries(
        stock_code,
        stock_name,
        [item.strip() for item in extra.split(",") if item.strip()],
        industry,
        topic_labels,
    )
    st.caption("将搜索以下情报主题：")
    render_query_ribbon(preview_queries, limit=16)
    submitted = st.form_submit_button("抓取并评分")

if submitted:
    keywords = [item.strip() for item in extra.split(",") if item.strip()]
    with st.spinner("正在抓取多源新闻并评分..."):
        items = service.collect_for_stock(stock_code, stock_name, keywords, limit=limit, industry=industry, topic_scope=topic_labels)
    source_counts = {}
    for item in items:
        source_counts[item["source"]] = source_counts.get(item["source"], 0) + 1
    st.success(f"已保存/更新 {len(items)} 条新闻证据。来源分布：{source_counts or '暂无'}")

evidence = service.get_evidence(stock_code if "stock_code" in locals() else "600519", limit=50)
sentiment = SentimentService().analyze(stock_code if "stock_code" in locals() else "600519")

usable_count = sum(1 for item in evidence if _quality_text(item) in {"高可信", "可用"})
render_kpi_grid(
    [
        ("消息面评分", f"{sentiment['news_score']:.1f}", sentiment["news_summary"][:30], "buy" if sentiment["news_score"] >= 60 else "watch"),
        ("风险等级", sentiment["news_risk_level"], "来自风险关键词和证据评分", "risk" if sentiment["news_risk_level"] != "low" else "neutral"),
        ("证据条数", str(len(evidence)), "已入库可复用", "neutral"),
        ("高可信/可用", str(usable_count), "可进入判断链", "buy" if usable_count else "watch"),
    ]
)
render_insight("消息面摘要", sentiment["news_summary"], "watch" if sentiment["news_risk_level"] != "low" else "neutral")

if evidence:
    render_copy_button("复制全部新闻分析", _news_copy_text(evidence), "news_copy_all", "复制当前股票全部新闻证据")
    rows = pd.DataFrame(
        [
            {
                "来源": item["source"],
                "标题": item["title"],
                "发布时间": item["published_at"],
                "事件": ", ".join(item.get("event_types", [])),
                "质量": _quality_text(item),
                "相关性": round(item["relevance_score"], 1),
                "可靠度": round(item["reliability_score"], 1),
                "情绪": round(item["sentiment_score"], 1),
                "风险词": ", ".join(item["risk_keywords"]),
                "利好词": ", ".join(item["positive_keywords"]),
                "金额/比例": ", ".join((item.get("extracted_entities") or {}).get("money", []) + (item.get("extracted_entities") or {}).get("percentages", [])),
                "链接": item["url"],
            }
            for item in evidence
        ]
    )
    f1, f2, f3 = st.columns([1, 1, 1])
    min_reliability = f1.slider("最低可靠度", 0, 100, 45)
    source_options = sorted(rows["来源"].dropna().unique().tolist())
    selected_sources = f2.multiselect("来源筛选", source_options, default=source_options)
    only_risk = f3.toggle("只看风险证据", value=False)
    filtered = rows[(rows["可靠度"] >= min_reliability) & (rows["来源"].isin(selected_sources))]
    if only_risk:
        filtered = filtered[filtered["风险词"].astype(str).str.len() > 0]
    render_copy_button("复制筛选后的新闻", _news_copy_text(filtered), "news_copy_filtered", "复制当前筛选结果")

    chart_cols = st.columns([1, 1])
    with chart_cols[0]:
        fig = px.bar(rows.groupby("来源", as_index=False).size(), x="来源", y="size", title="来源覆盖")
        st.plotly_chart(apply_chart_interaction(fig, y_title="数量", x_title="来源"), width="stretch", key="news_source_coverage")
    with chart_cols[1]:
        fig = px.histogram(rows, x="可靠度", nbins=10, title="可靠度分布")
        st.plotly_chart(apply_chart_interaction(fig, y_title="数量", x_title="可靠度"), width="stretch", key="news_reliability_histogram")
    event_rows = rows.assign(事件拆分=rows["事件"].str.split(", ")).explode("事件拆分")
    event_rows = event_rows[event_rows["事件拆分"].fillna("") != ""]
    if not event_rows.empty:
        fig = px.bar(event_rows.groupby("事件拆分", as_index=False).size(), x="事件拆分", y="size", title="事件类型覆盖")
        st.plotly_chart(apply_chart_interaction(fig, y_title="数量", x_title="事件类型"), width="stretch", key="news_event_coverage")

    st.markdown(
        "".join(
            badge(item["title"][:18], "risk" if item["risk_keywords"] else "buy" if item["positive_keywords"] else "neutral")
            for item in evidence[:8]
        ),
        unsafe_allow_html=True,
    )
    render_static_table(
        filtered.to_dict("records"),
        ["来源", "标题", "发布时间", "事件", "质量", "相关性", "可靠度", "情绪", "风险词", "利好词", "链接"],
        max_cell_length=180,
    )
    if filtered.empty:
        st.warning("当前筛选条件下没有证据，可降低可靠度阈值或放宽来源筛选。")
        st.stop()
    selected_title = st.selectbox("查看证据详情", filtered["标题"].tolist())
    selected = next(item for item in evidence if item["title"] == selected_title)
    render_link_card(
        selected["title"],
        selected.get("url", ""),
        f"{selected['evidence_reason']} 摘要：{selected.get('summary') or '-'}",
        _quality_tone(selected),
    )
    st.json({"event_types": selected.get("event_types", []), "entities": selected.get("extracted_entities", {})})
else:
    st.info("暂无新闻证据。请先点击抓取。")
