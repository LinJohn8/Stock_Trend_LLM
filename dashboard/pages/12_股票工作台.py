from __future__ import annotations

from html import escape

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.ui import (
    action_tone,
    apply_chart_interaction,
    badge,
    inject_global_style,
    render_hero,
    render_kpi_grid,
    render_link_card,
    render_loading_panel,
    render_copy_button,
    render_static_table,
)
from database.db import init_db
from services.ai_analysis_service import AIAnalysisService
from services.algorithm_service import AlgorithmService
from services.llm_skill_service import LLMReviewSkillService
from services.news_ingestion_service import NewsIngestionService
from services.signal_service import SignalService
from services.stock_data_service import StockDataService

st.set_page_config(page_title="股票工作台", layout="wide")
init_db()
inject_global_style()

data_service = StockDataService()
news_service = NewsIngestionService()
algorithm_service = AlgorithmService()
signal_service = SignalService()
skill_service = LLMReviewSkillService()
ai_service = AIAnalysisService()

render_hero(
    "股票全流程工作台",
    "一个页面完成：行情图表、新闻证据、算法组合、规则信号、LLM 上下文和右侧 AI 问答。点击按钮才触发重任务，避免页面打开就卡。",
    "One Click Research Deck",
    [("一键全流程", "buy"), ("新闻可点击", "neutral"), ("AI 对话", "watch")],
)

if "workbench_chat" not in st.session_state:
    st.session_state["workbench_chat"] = []
if "workbench_latest_answer" not in st.session_state:
    st.session_state["workbench_latest_answer"] = ""


def _df_markdown(df: pd.DataFrame, limit: int = 30) -> str:
    if df is None or df.empty:
        return "暂无数据"
    return df.tail(limit).to_markdown(index=False)


def _quote_copy(snapshot: dict | None) -> str:
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


def _table_copy(snapshot: dict | None) -> str:
    if not snapshot:
        return "暂无数据表，请先读取行情。"
    return "\n\n".join(
        [
            "# 数据表分析",
            "## 最近日线",
            _df_markdown(snapshot["daily"], 40),
            "## 周线",
            _df_markdown(snapshot["weekly"], 20),
            "## 近 5 日",
            _df_markdown(snapshot["recent_5d"], 5),
            "## 分时",
            _df_markdown(snapshot["intraday"], 40),
        ]
    )


def _news_copy(news_items: list[dict]) -> str:
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


def _signal_copy(signal: dict | None) -> str:
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


def _algorithm_copy(algorithm: dict | None) -> str:
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


def _context_copy(context: dict | None) -> str:
    if not context:
        return "暂无 LLM 上下文，请先点击“一键全流程分析”。"
    return "# LLM 上下文\n" + str(context)


def _all_copy(snapshot: dict | None, news_items: list[dict], signal: dict | None, algorithm: dict | None, context: dict | None) -> str:
    return "\n\n---\n\n".join(
        [
            _quote_copy(snapshot),
            _table_copy(snapshot),
            _news_copy(news_items),
            _signal_copy(signal),
            _algorithm_copy(algorithm),
            _context_copy(context),
        ]
    )

top = st.columns([1, 1, 1, 1.4])
stock_code = top[0].text_input("股票代码", value=st.session_state.get("workbench_code", "600519"))
stock_name = top[1].text_input("股票名称", value=st.session_state.get("workbench_name", "贵州茅台"))
refresh = top[2].toggle("强制刷新行情", value=False)
top[3].caption("建议流程：先点击“一键全流程分析”，右侧再基于结果提问。")

screening_context = st.session_state.get("workbench_from_screening")
if screening_context:
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

run_cols = st.columns([1, 1, 1, 2])
run_all = run_cols[0].button("一键全流程分析", type="primary", width="stretch")
run_quote = run_cols[1].button("只看行情", width="stretch")
run_news = run_cols[2].button("只抓新闻", width="stretch")
run_cols[3].info("全流程会依次读取行情、抓取新闻、运行规则信号、运行算法组合并构建 AI 上下文。")

if run_all or run_quote or run_news:
    st.session_state["workbench_code"] = stock_code
    st.session_state["workbench_name"] = stock_name

if run_quote or run_all:
    with st.spinner("正在读取行情数据..."):
        render_loading_panel("行情读取中", "正在获取实时价、日 K、周 K、近 5 日和分时。")
        st.session_state["workbench_snapshot"] = data_service.get_market_snapshot(stock_code, refresh=refresh)

if run_news or run_all:
    with st.spinner("正在抓取并评分新闻..."):
        render_loading_panel("新闻证据处理中", "正在检索公告、个股、行业和市场情绪来源。")
        st.session_state["workbench_news"] = news_service.collect_for_stock(
            stock_code,
            stock_name,
            limit=30,
            industry=stock_name,
            topic_scope=["stock", "announcement", "industry", "market_sentiment"],
        )

if run_all:
    with st.spinner("正在运行规则信号与组合算法..."):
        render_loading_panel("分析引擎运行中", "正在融合技术、基本面、新闻、风控和学习记忆。")
        st.session_state["workbench_signal"] = signal_service.analyze_stock(stock_code, stock_name)
        st.session_state["workbench_algorithm"] = algorithm_service.run(stock_code, stock_name, fetch_data=False)
        st.session_state["workbench_context"] = skill_service.build_computed_context(stock_code, stock_name)

main_col, chat_col = st.columns([2.25, 0.95], gap="large")

snapshot_for_copy = st.session_state.get("workbench_snapshot")
news_for_copy = st.session_state.get("workbench_news") or news_service.get_evidence(stock_code, limit=12)
signal_for_copy = st.session_state.get("workbench_signal")
algorithm_for_copy = st.session_state.get("workbench_algorithm")
context_for_copy = st.session_state.get("workbench_context")
render_copy_button(
    "一键复制全部数据与分析",
    _all_copy(snapshot_for_copy, news_for_copy, signal_for_copy, algorithm_for_copy, context_for_copy),
    "workbench_copy_all",
    "复制行情、数据表、新闻、信号、算法和 LLM 上下文",
)

with main_col:
    snapshot = st.session_state.get("workbench_snapshot")
    if snapshot:
        copy_cols = st.columns([1, 1, 2])
        with copy_cols[0]:
            render_copy_button("复制行情分析", _quote_copy(snapshot), "workbench_copy_quote")
        with copy_cols[1]:
            render_copy_button("复制数据表分析", _table_copy(snapshot), "workbench_copy_tables")
        quote = snapshot["quote"]
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
        chart_tabs = st.tabs(["日 K", "周 K", "近 5 日", "分时", "数据表"])
        with chart_tabs[0]:
            daily = snapshot["daily"].tail(160)
            if daily.empty:
                st.warning("暂无日线数据。")
            else:
                chart_df = daily.copy()
                chart_df["MA5"] = chart_df["close"].rolling(5).mean()
                chart_df["MA20"] = chart_df["close"].rolling(20).mean()
                fig = px.line(chart_df, x="date", y=["close", "MA5", "MA20"], title="日 K 收盘与均线")
                fig.update_traces(hovertemplate="%{x}<br>%{fullData.name} %{y:.2f}<extra></extra>")
                st.plotly_chart(apply_chart_interaction(fig, y_title="价格", x_title="日期"), width="stretch", key="workbench_daily")
        with chart_tabs[1]:
            weekly = snapshot["weekly"]
            if weekly.empty:
                st.warning("暂无周线数据。")
            else:
                fig = px.line(weekly, x="date", y="close", title="周 K 收盘走势")
                fig.update_traces(hovertemplate="%{x}<br>周收盘 %{y:.2f}<extra></extra>")
                st.plotly_chart(apply_chart_interaction(fig, y_title="价格", x_title="日期"), width="stretch", key="workbench_weekly")
        with chart_tabs[2]:
            recent = snapshot["recent_5d"]
            if recent.empty:
                st.warning("暂无近 5 日数据。")
            else:
                fig = px.line(recent, x="date", y="close", markers=True, title="近 5 日")
                fig.update_traces(hovertemplate="%{x}<br>收盘 %{y:.2f}<extra></extra>")
                st.plotly_chart(apply_chart_interaction(fig, y_title="价格", x_title="日期"), width="stretch", key="workbench_5d")
        with chart_tabs[3]:
            intraday = snapshot["intraday"]
            if intraday.empty:
                st.info("当前没有分时数据，可能是非交易时段或接口暂不可用。")
            else:
                fig = px.line(intraday, x="time", y="price", title="当日分时")
                fig.update_traces(hovertemplate="%{x}<br>价格 %{y:.2f}<extra></extra>")
                st.plotly_chart(apply_chart_interaction(fig, y_title="价格", x_title="时间"), width="stretch", key="workbench_intraday")
        with chart_tabs[4]:
            render_static_table(snapshot["daily"].tail(40).to_dict("records"), ["date", "open", "high", "low", "close", "volume", "pct_change"])

    signal = st.session_state.get("workbench_signal")
    algorithm = st.session_state.get("workbench_algorithm")
    if signal or algorithm:
        st.subheader("分析结论")
        analysis_copy_cols = st.columns([1, 1, 2])
        with analysis_copy_cols[0]:
            render_copy_button("复制规则信号", _signal_copy(signal), "workbench_copy_signal")
        with analysis_copy_cols[1]:
            render_copy_button("复制算法分析", _algorithm_copy(algorithm), "workbench_copy_algorithm")
        cards = []
        if signal:
            cards.append(("规则信号", signal["action"], f"评分 {signal['overall_score']:.1f}", action_tone(signal["action"])))
        if algorithm:
            cards.append(("组合算法", algorithm["action"], f"评分 {algorithm['overall_score']:.1f}", action_tone(algorithm["action"])))
        render_kpi_grid(cards)
        if signal:
            st.markdown(
                "<div class='decision-card'>"
                f"{badge(signal['action'], action_tone(signal['action']))}"
                f"<div class='mini-note'>{signal['reason']}</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        if algorithm:
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

    news_items = st.session_state.get("workbench_news") or news_service.get_evidence(stock_code, limit=12)
    st.subheader("新闻证据")
    render_copy_button("复制新闻分析", _news_copy(news_items), "workbench_copy_news")
    if news_items:
        for item in news_items[:12]:
            score = float(item.get("reliability_score") or 0)
            tone = "buy" if score >= 70 else "watch" if score >= 45 else "risk"
            meta = f"{item.get('source', '-')} | 可靠度 {score:.1f} | 相关性 {float(item.get('relevance_score') or 0):.1f}"
            render_link_card(item.get("title", "未命名新闻"), item.get("url", ""), meta, tone)
    else:
        st.info("暂无新闻证据。点击“只抓新闻”或“一键全流程分析”。")

with chat_col:
    st.markdown("<div class='chat-panel'><strong>AI 侧边问答</strong><div class='mini-note'>基于当前页面已有行情、新闻和算法结果回答。未配置 API Key 时使用本地规则答复。</div></div>", unsafe_allow_html=True)
    question = st.text_area("向 AI 提问", value="这只股票现在主要风险是什么？", height=110)
    if st.button("发送给 AI", type="primary", width="stretch", disabled=not question.strip()):
        context = {
            "quote": (st.session_state.get("workbench_snapshot") or {}).get("quote", {}),
            "technical": (st.session_state.get("workbench_context") or {}).get("technical", {}),
            "sentiment": (st.session_state.get("workbench_context") or {}).get("sentiment", {}),
            "news_evidence": st.session_state.get("workbench_news") or news_service.get_evidence(stock_code, limit=8),
            "signal": st.session_state.get("workbench_signal"),
            "algorithm": st.session_state.get("workbench_algorithm"),
        }
        with st.spinner("AI 正在基于当前证据回答..."):
            answer = ai_service.chat_about_stock(question, context)
        st.session_state["workbench_chat"].append({"q": question, "a": answer})
        st.session_state["workbench_latest_answer"] = answer
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
    else:
        st.markdown(
            "<div class='chat-panel' style='border-left-color:var(--blue);'>"
            "<strong>最新 AI 回复会显示在这里</strong>"
            "<div class='mini-note'>发送问题后，这里会固定展示最新答复，下方保留最近对话历史。</div>"
            "</div>",
            unsafe_allow_html=True,
        )
    for message in reversed(st.session_state["workbench_chat"][-6:]):
        st.markdown(
            "<div class='chat-panel'>"
            f"<strong>Q：</strong>{escape(message['q'])}"
            f"<div class='chat-answer'><strong>A：</strong>{escape(message['a'])}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
