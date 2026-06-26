from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.ui import (
    action_tone,
    apply_chart_interaction,
    badge,
    render_anchor,
    render_copy_button,
    render_dock_panel,
    render_kpi_grid,
    render_link_card,
    render_section_shell,
    render_static_table,
)
from services.ai_analysis_service import AIAnalysisService


def init_workbench_state() -> None:
    st.session_state.setdefault("workbench_chat", [])
    st.session_state.setdefault("workbench_latest_answer", "")


def df_markdown(df: pd.DataFrame, limit: int = 30) -> str:
    if df is None or df.empty:
        return "暂无数据"
    return df.tail(limit).to_markdown(index=False)


def quote_copy(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return "暂无行情数据，请先点击“只看行情”或“一键全流程分析”。"
    quote = snapshot["quote"]
    return "\n".join(
        [
            "# 行情摘要",
            f"股票：{quote.get('stock_code')} {quote.get('stock_name') or ''}",
            f"最新价：{quote.get('current_price')}",
            f"涨跌幅：{quote.get('pct_change')}%",
            f"开高低昨收：{quote.get('open')} / {quote.get('high')} / {quote.get('low')} / {quote.get('prev_close')}",
            f"成交量：{quote.get('volume')}，成交额：{quote.get('amount')}",
            f"PE/PB：{quote.get('pe')} / {quote.get('pb')}",
            f"数据源：{quote.get('source')}",
        ]
    )


def table_copy(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return "暂无数据表，请先读取行情。"
    return "\n\n".join(
        [
            "# 数据表分析",
            "## 最近日线",
            df_markdown(snapshot["daily"], 40),
            "## 周线",
            df_markdown(snapshot["weekly"], 20),
            "## 近 5 日",
            df_markdown(snapshot["recent_5d"], 5),
            "## 分时",
            df_markdown(snapshot["intraday"], 40),
        ]
    )


def news_copy(news_items: list[dict[str, Any]]) -> str:
    if not news_items:
        return "暂无新闻证据，请先点击“只抓新闻”或“一键全流程分析”。"
    lines = ["# 新闻分析"]
    for idx, item in enumerate(news_items[:20], start=1):
        lines.extend(
            [
                f"{idx}. {item.get('title', '-')}",
                f"   来源：{item.get('source', '-')} | 可靠度：{item.get('reliability_score', '-')} | 相关性：{item.get('relevance_score', '-')}",
                f"   摘要：{item.get('summary') or item.get('evidence_reason') or '-'}",
                f"   链接：{item.get('url', '-')}",
            ]
        )
    return "\n".join(lines)


def signal_copy(signal: dict[str, Any] | None) -> str:
    if not signal:
        return "暂无规则信号，请先点击“一键全流程分析”。"
    return "\n".join(
        [
            "# 规则信号分析",
            f"动作：{signal.get('action')}",
            f"综合评分：{signal.get('overall_score')}，置信度：{signal.get('confidence')}",
            f"建议仓位：{signal.get('suggested_position')}",
            f"止损价：{signal.get('stop_loss_price')}，止盈价：{signal.get('take_profit_price')}",
            f"理由：{signal.get('reason')}",
            f"风险点：{'；'.join(signal.get('risk_points', []))}",
            f"失效条件：{'；'.join(signal.get('invalidation_conditions', []))}",
        ]
    )


def algorithm_copy(algorithm: dict[str, Any] | None) -> str:
    if not algorithm:
        return "暂无算法分析，请先点击“一键全流程分析”。"
    lines = [
        "# 算法组合分析",
        f"动作：{algorithm.get('action')}",
        f"综合评分：{algorithm.get('overall_score')}，置信度：{algorithm.get('confidence')}",
        f"摘要：{algorithm.get('summary')}",
        "## 子算法",
    ]
    for item in algorithm.get("results", []):
        lines.append(
            f"- {item.get('name')}：评分 {item.get('score')}，方向 {item.get('direction')}，"
            f"理由 {'；'.join(item.get('reasons', []))}，风险 {'；'.join(item.get('risks', []))}"
        )
    lines.append(f"组合细节：{algorithm.get('combination')}")
    return "\n".join(lines)


def context_copy(context: dict[str, Any] | None) -> str:
    if not context:
        return "暂无 LLM 上下文，请先点击“一键全流程分析”。"
    return "# LLM 上下文\n" + str(context)


def all_copy(
    snapshot: dict[str, Any] | None,
    news_items: list[dict[str, Any]],
    signal: dict[str, Any] | None,
    algorithm: dict[str, Any] | None,
    context: dict[str, Any] | None,
) -> str:
    return "\n\n---\n\n".join(
        [
            quote_copy(snapshot),
            table_copy(snapshot),
            news_copy(news_items),
            signal_copy(signal),
            algorithm_copy(algorithm),
            context_copy(context),
        ]
    )


def render_screening_status(screening_context: dict[str, Any] | None) -> None:
    if not screening_context:
        return
    st.markdown(
        "<div class='status-strip'>"
        "<strong>来自选股模拟：</strong>"
        f"资金 {float(screening_context.get('cash', 0)):,.0f}，"
        f"一手价格上限 {float(screening_context.get('one_lot_price_limit', 0)):.2f}，"
        f"候选排名 #{screening_context.get('rank', '-')}，初筛评分 {screening_context.get('score', '-')}。"
        f"<div class='mini-note'>初筛理由：{escape('；'.join(screening_context.get('reasons', [])[:3]))}</div>"
        f"<div class='mini-note'>初筛风险：{escape('；'.join(screening_context.get('risks', [])[:3]))}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_market_section(snapshot: dict[str, Any] | None) -> None:
    render_anchor("workbench-market")
    render_section_shell("行情图表与数据桌面", "日 K、周 K、近 5 日、分时和原始数据表集中在这里；图表支持十字光标、悬浮价格和缩放拖拽。", "Market Console")
    with st.expander("行情图表 / K 线 / 数据表", expanded=bool(snapshot)):
        if not snapshot:
            st.info("点击“只看行情”或“一键全流程分析”后显示行情图表。")
            return
        copy_cols = st.columns([1, 1, 2])
        with copy_cols[0]:
            render_copy_button("复制行情分析", quote_copy(snapshot), "workbench_copy_quote")
        with copy_cols[1]:
            render_copy_button("复制数据表分析", table_copy(snapshot), "workbench_copy_tables")
        _render_quote_kpis(snapshot["quote"])
        _render_market_tabs(snapshot)


def render_analysis_section(signal: dict[str, Any] | None, algorithm: dict[str, Any] | None) -> None:
    render_anchor("workbench-analysis")
    render_section_shell("分析结论与算法证据", "规则信号和组合算法分开展示，便于复制、复核和定位某个算法的贡献。", "Analysis Layer")
    with st.expander("分析结论 / 规则信号 / 算法组合", expanded=bool(signal or algorithm)):
        if not (signal or algorithm):
            st.info("点击“一键全流程分析”后显示规则信号和算法组合结果。")
            return
        analysis_copy_cols = st.columns([1, 1, 2])
        with analysis_copy_cols[0]:
            render_copy_button("复制规则信号", signal_copy(signal), "workbench_copy_signal")
        with analysis_copy_cols[1]:
            render_copy_button("复制算法分析", algorithm_copy(algorithm), "workbench_copy_algorithm")
        _render_analysis_kpis(signal, algorithm)
        _render_signal_card(signal)
        _render_algorithm_table(algorithm)


def render_news_section(news_items: list[dict[str, Any]]) -> None:
    render_anchor("workbench-news")
    render_section_shell("新闻证据与来源跳转", "新闻链接改为可点击卡片，保留来源、可靠度、相关性，适合快速复核信息来源。", "Evidence Feed")
    with st.expander("新闻证据 / 可点击来源 / 复制新闻", expanded=bool(news_items)):
        render_copy_button("复制新闻分析", news_copy(news_items), "workbench_copy_news")
        if not news_items:
            st.info("暂无新闻证据。点击“只抓新闻”或“一键全流程分析”。")
            return
        for item in news_items[:12]:
            score = float(item.get("reliability_score") or 0)
            tone = "buy" if score >= 70 else "watch" if score >= 45 else "risk"
            meta = f"{item.get('source', '-')} | 可靠度 {score:.1f} | 相关性 {float(item.get('relevance_score') or 0):.1f}"
            render_link_card(item.get("title", "未命名新闻"), item.get("url", ""), meta, tone)


def render_ai_research_panel(ai_service: AIAnalysisService) -> None:
    init_workbench_state()
    render_anchor("workbench-ai")
    render_dock_panel("AI 侧边研究员", "固定在右侧的小对话框会基于当前页面已有行情、新闻、规则信号和算法结果回答；未配置 API Key 时使用本地规则答复。")
    render_copy_hub(
        st.session_state.get("workbench_snapshot"),
        st.session_state.get("workbench_news") or [],
        st.session_state.get("workbench_signal"),
        st.session_state.get("workbench_algorithm"),
        st.session_state.get("workbench_context"),
    )
    question = st.text_area("向 AI 提问", value="这只股票现在主要风险是什么？", height=110)
    if st.button("发送给 AI", type="primary", width="stretch", disabled=not question.strip()):
        with st.spinner("AI 正在基于当前证据回答..."):
            answer = ai_service.chat_about_stock(question, _current_ai_context())
        st.session_state["workbench_chat"].append({"q": question, "a": answer})
        st.session_state["workbench_latest_answer"] = answer
    _render_latest_ai_answer()
    _render_chat_history()


def render_copy_hub(
    snapshot: dict[str, Any] | None,
    news_items: list[dict[str, Any]],
    signal: dict[str, Any] | None,
    algorithm: dict[str, Any] | None,
    context: dict[str, Any] | None,
) -> None:
    available_count = sum(bool(item) for item in [snapshot, news_items, signal, algorithm, context])
    with st.container(key="workbench_copy_hub"):
        st.markdown(
            "<div class='copy-hub'>"
            "<div class='copy-hub-title'>"
            "<span>固定复制区</span>"
            f"<span class='copy-hub-pill'>{available_count}/5 已有内容</span>"
            "</div>"
            "<div class='mini-note'>常用分析内容集中在这里，方便一边和 AI 对话一边复制。</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        render_copy_button("一键复制全部", all_copy(snapshot, news_items, signal, algorithm, context), "workbench_side_copy_all", "行情 / 表格 / 新闻 / 信号 / 算法 / LLM 上下文")
        with st.expander("展开单项复制", expanded=False):
            render_copy_button("复制行情", quote_copy(snapshot), "workbench_side_copy_quote")
            render_copy_button("复制数据表", table_copy(snapshot), "workbench_side_copy_tables")
            render_copy_button("复制规则信号", signal_copy(signal), "workbench_side_copy_signal")
            render_copy_button("复制算法分析", algorithm_copy(algorithm), "workbench_side_copy_algorithm")
            render_copy_button("复制新闻分析", news_copy(news_items), "workbench_side_copy_news")
            render_copy_button("复制 LLM 上下文", context_copy(context), "workbench_side_copy_context")


def _render_quote_kpis(quote: dict[str, Any]) -> None:
    pct = quote.get("pct_change")
    tone = "buy" if pct is not None and pct > 0 else "risk" if pct is not None and pct < 0 else "neutral"
    render_kpi_grid(
        [
            ("最新价", "-" if quote.get("current_price") is None else f"{quote['current_price']:.2f}", f"来源 {quote.get('source', '-')}", tone),
            ("涨跌幅", "-" if pct is None else f"{pct:.2f}%", "实时/缓存行情", tone),
            ("成交额", "-" if quote.get("amount") is None else f"{float(quote['amount']) / 100000000:.2f} 亿", "资金活跃度", "neutral"),
            ("PE/PB", f"{quote.get('pe') or '-'} / {quote.get('pb') or '-'}", "估值快照", "watch"),
        ]
    )


def _render_market_tabs(snapshot: dict[str, Any]) -> None:
    chart_tabs = st.tabs(["日 K", "周 K", "近 5 日", "分时", "数据表"])
    with chart_tabs[0]:
        _render_daily_chart(snapshot["daily"])
    with chart_tabs[1]:
        _render_weekly_chart(snapshot["weekly"])
    with chart_tabs[2]:
        _render_recent_chart(snapshot["recent_5d"])
    with chart_tabs[3]:
        _render_intraday_chart(snapshot["intraday"])
    with chart_tabs[4]:
        render_static_table(snapshot["daily"].tail(40).to_dict("records"), ["date", "open", "high", "low", "close", "volume", "pct_change"])


def _render_daily_chart(daily: pd.DataFrame) -> None:
    daily = daily.tail(160)
    if daily.empty:
        st.warning("暂无日线数据。")
        return
    chart_df = daily.copy()
    chart_df["MA5"] = chart_df["close"].rolling(5).mean()
    chart_df["MA20"] = chart_df["close"].rolling(20).mean()
    fig = px.line(chart_df, x="date", y=["close", "MA5", "MA20"], title="日 K 收盘与均线")
    fig.update_traces(hovertemplate="%{x}<br>%{fullData.name} %{y:.2f}<extra></extra>")
    st.plotly_chart(apply_chart_interaction(fig, y_title="价格", x_title="日期"), width="stretch", key="workbench_daily")


def _render_weekly_chart(weekly: pd.DataFrame) -> None:
    if weekly.empty:
        st.warning("暂无周线数据。")
        return
    fig = px.line(weekly, x="date", y="close", title="周 K 收盘走势")
    fig.update_traces(hovertemplate="%{x}<br>周收盘 %{y:.2f}<extra></extra>")
    st.plotly_chart(apply_chart_interaction(fig, y_title="价格", x_title="日期"), width="stretch", key="workbench_weekly")


def _render_recent_chart(recent: pd.DataFrame) -> None:
    if recent.empty:
        st.warning("暂无近 5 日数据。")
        return
    fig = px.line(recent, x="date", y="close", markers=True, title="近 5 日")
    fig.update_traces(hovertemplate="%{x}<br>收盘 %{y:.2f}<extra></extra>")
    st.plotly_chart(apply_chart_interaction(fig, y_title="价格", x_title="日期"), width="stretch", key="workbench_5d")


def _render_intraday_chart(intraday: pd.DataFrame) -> None:
    if intraday.empty:
        st.info("当前没有分时数据，可能是非交易时段或接口暂不可用。")
        return
    fig = px.line(intraday, x="time", y="price", title="当日分时")
    fig.update_traces(hovertemplate="%{x}<br>价格 %{y:.2f}<extra></extra>")
    st.plotly_chart(apply_chart_interaction(fig, y_title="价格", x_title="时间"), width="stretch", key="workbench_intraday")


def _render_analysis_kpis(signal: dict[str, Any] | None, algorithm: dict[str, Any] | None) -> None:
    cards = []
    if signal:
        cards.append(("规则信号", signal["action"], f"评分 {signal['overall_score']:.1f}", action_tone(signal["action"])))
    if algorithm:
        cards.append(("组合算法", algorithm["action"], f"评分 {algorithm['overall_score']:.1f}", action_tone(algorithm["action"])))
    render_kpi_grid(cards)


def _render_signal_card(signal: dict[str, Any] | None) -> None:
    if not signal:
        return
    st.markdown(
        "<div class='decision-card'>"
        f"{badge(signal['action'], action_tone(signal['action']))}"
        f"<div class='mini-note'>{signal['reason']}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_algorithm_table(algorithm: dict[str, Any] | None) -> None:
    if not algorithm:
        return
    result_rows = [
        {
            "算法": item["name"],
            "评分": round(item["score"], 1),
            "方向": item.get("direction", "neutral"),
            "理由": "；".join(item.get("reasons", [])),
            "风险": "；".join(item.get("risks", [])),
        }
        for item in algorithm.get("results", [])
    ]
    render_static_table(result_rows, ["算法", "评分", "方向", "理由", "风险"], max_cell_length=220)


def _current_ai_context() -> dict[str, Any]:
    return {
        "quote": (st.session_state.get("workbench_snapshot") or {}).get("quote", {}),
        "technical": (st.session_state.get("workbench_context") or {}).get("technical", {}),
        "sentiment": (st.session_state.get("workbench_context") or {}).get("sentiment", {}),
        "news_evidence": st.session_state.get("workbench_news") or [],
        "signal": st.session_state.get("workbench_signal"),
        "algorithm": st.session_state.get("workbench_algorithm"),
    }


def _render_latest_ai_answer() -> None:
    latest_answer = st.session_state.get("workbench_latest_answer")
    if latest_answer:
        st.markdown(
            "<div class='chat-panel' style='border-left-color:var(--green);'>"
            "<strong>最新 AI 回复</strong>"
            f"<div class='chat-answer'>{escape(latest_answer)}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        render_copy_button("复制最新 AI 回复", latest_answer, "workbench_copy_latest_ai")
        return
    st.markdown(
        "<div class='chat-panel' style='border-left-color:var(--blue);'>"
        "<strong>最新 AI 回复会显示在这里</strong>"
        "<div class='mini-note'>发送问题后，这里会固定展示最新答复；不再隐藏在页面底部。</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_chat_history() -> None:
    for message in reversed(st.session_state["workbench_chat"][-6:]):
        st.markdown(
            "<div class='chat-panel'>"
            f"<strong>Q：</strong>{escape(message['q'])}"
            f"<div class='chat-answer'><strong>A：</strong>{escape(message['a'])}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
