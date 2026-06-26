from __future__ import annotations

import streamlit as st

from dashboard.ui import (
    inject_global_style,
    render_hero,
    render_loading_panel,
    render_anchor,
    render_page_nav,
)
from dashboard.workbench_view import (
    init_workbench_state,
    render_ai_research_panel,
    render_analysis_section,
    render_market_section,
    render_news_section,
    render_screening_status,
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
render_page_nav(
    [
        ("顶部/操作", "workbench-top"),
        ("行情图表", "workbench-market"),
        ("分析结论", "workbench-analysis"),
        ("新闻证据", "workbench-news"),
        ("AI 对话", "workbench-ai"),
    ]
)
render_anchor("workbench-top")

init_workbench_state()

top = st.columns([1, 1, 1, 1.4])
stock_code = top[0].text_input("股票代码", value=st.session_state.get("workbench_code", "600519"))
stock_name = top[1].text_input("股票名称", value=st.session_state.get("workbench_name", "贵州茅台"))
refresh = top[2].toggle("强制刷新行情", value=False)
top[3].caption("建议流程：先点击“一键全流程分析”，右侧再基于结果提问。")

render_screening_status(st.session_state.get("workbench_from_screening"))

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

main_col, ai_col = st.columns([2.25, 0.95], gap="large")

with main_col:
    render_market_section(st.session_state.get("workbench_snapshot"))
    render_analysis_section(st.session_state.get("workbench_signal"), st.session_state.get("workbench_algorithm"))
    render_news_section(st.session_state.get("workbench_news") or [])

with ai_col:
    render_ai_research_panel(ai_service)
