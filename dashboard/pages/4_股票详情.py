from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dashboard.ui import action_tone, apply_chart_interaction, badge, inject_global_style, render_hero, render_insight, render_kpi_grid, render_timeline
from database.db import init_db
from services.algorithm_service import AlgorithmService
from services.indicator_service import IndicatorService
from services.llm_skill_service import LLMReviewSkillService
from services.news_ingestion_service import NewsIngestionService
from services.signal_service import SignalService
from services.stock_data_service import StockDataService

st.set_page_config(page_title="股票详情", layout="wide")
init_db()
inject_global_style()


def _pct(value) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def _money(value) -> str:
    if value is None:
        return "-"
    value = float(value)
    if abs(value) >= 100000000:
        return f"{value / 100000000:.2f} 亿"
    if abs(value) >= 10000:
        return f"{value / 10000:.2f} 万"
    return f"{value:.0f}"


def _candlestick(df: pd.DataFrame, title: str):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.04)
    fig.add_trace(go.Candlestick(x=df["date"], open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="K线"), row=1, col=1)
    for window in [5, 20, 60]:
        if len(df) >= window:
            fig.add_trace(go.Scatter(x=df["date"], y=df["close"].rolling(window).mean(), name=f"MA{window}", mode="lines"), row=1, col=1)
    fig.add_trace(go.Bar(x=df["date"], y=df["volume"], name="成交量"), row=2, col=1)
    fig.update_layout(title=title, height=620, xaxis_rangeslider_visible=False)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    return apply_chart_interaction(fig, y_title="价格", x_title="日期")


def _line(df: pd.DataFrame, x: str, y: str, title: str):
    fig = px.line(df, x=x, y=y, title=title)
    fig.update_traces(hovertemplate="%{x}<br>价格 %{y:.2f}<extra></extra>")
    fig.update_layout(height=420)
    return apply_chart_interaction(fig, y_title="价格", x_title="时间")


def _price_amount_chart(df: pd.DataFrame, title: str):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=df["date"], y=df["close"], mode="lines", name="收盘价"), secondary_y=False)
    if "amount" in df:
        fig.add_trace(go.Bar(x=df["date"], y=df["amount"], name="成交额", opacity=0.28), secondary_y=True)
    fig.update_layout(title=title, height=420)
    fig.update_yaxes(title_text="价格", secondary_y=False)
    fig.update_yaxes(title_text="成交额", secondary_y=True)
    return apply_chart_interaction(fig, y_title="价格", x_title="日期")


def _source_status(snapshot: dict) -> list[tuple[str, str]]:
    daily = snapshot.get("daily")
    weekly = snapshot.get("weekly")
    recent = snapshot.get("recent_5d")
    intraday = snapshot.get("intraday")
    return [
        ("实时行情", "已加载" if snapshot.get("quote", {}).get("current_price") is not None else "降级/缺失"),
        ("日 K", f"{len(daily) if daily is not None else 0} 行"),
        ("周 K", f"{len(weekly) if weekly is not None else 0} 行"),
        ("近 5 日", f"{len(recent) if recent is not None else 0} 行"),
        ("分时", f"{len(intraday)} 行" if intraday is not None and not intraday.empty else "接口暂无"),
    ]


def _status_tone(value: str) -> str:
    if value.startswith("0 ") or "缺失" in value or "接口暂无" in value:
        return "watch"
    if "已加载" in value or "行" in value:
        return "buy"
    return "neutral"


data_service = StockDataService()
algorithm_service = AlgorithmService()
skill_service = LLMReviewSkillService()

top = st.container()
with top:
    cols = st.columns([1, 1, 1, 2])
    code = cols[0].text_input("股票代码", value=st.session_state.get("detail_stock_code", "600519"), placeholder="600519")
    refresh = cols[1].button("刷新数据", width="stretch")
    clear_cache = cols[2].button("清除页面缓存", width="stretch")
    cols[3].caption("输入代码后会自动补全名称、最新价、日 K、周 K、近 5 日和分时；刷新会重新拉取数据。")

if clear_cache:
    for key in ["detail_snapshot", "detail_snapshot_code"]:
        st.session_state.pop(key, None)
    st.toast("页面行情缓存已清除。")

if code:
    st.session_state["detail_stock_code"] = code
    try:
        with st.spinner("正在读取行情数据..."):
            if refresh or "detail_snapshot_code" not in st.session_state or st.session_state.get("detail_snapshot_code") != code:
                st.session_state["detail_snapshot"] = data_service.get_market_snapshot(code, refresh=refresh)
                st.session_state["detail_snapshot_code"] = code
            snapshot = st.session_state["detail_snapshot"]
    except Exception as exc:
        st.error(f"行情读取失败：{exc}")
        st.stop()

    quote = snapshot["quote"]
    stock_name = quote.get("stock_name") or ""
    pct = quote.get("pct_change")
    tone = "buy" if pct is not None and pct > 0 else "risk" if pct is not None and pct < 0 else "neutral"
    render_hero(
        f"{quote['stock_code']} {stock_name or '名称待获取'}",
        f"实时源：{quote.get('source', 'unknown')}。日线、周线、近 5 日和分时在同一页面联动展示；分析区会把行情、新闻、算法和 LLM 上下文串成可审计流程。",
        "Single Stock Command Deck",
        [(f"最新 {quote.get('current_price') or '-'}", tone), (f"涨跌幅 {_pct(pct)}", tone), (f"成交额 {_money(quote.get('amount'))}", "neutral")],
    )
    render_kpi_grid(
        [
            ("最新价", "-" if quote.get("current_price") is None else f"{quote['current_price']:.2f}", f"涨跌幅 {_pct(quote.get('pct_change'))}", tone),
            ("今开/最高", f"{quote.get('open') or '-'} / {quote.get('high') or '-'}", "盘中区间上沿", "neutral"),
            ("最低/昨收", f"{quote.get('low') or '-'} / {quote.get('prev_close') or '-'}", "盘中区间下沿", "neutral"),
            ("成交额", _money(quote.get("amount")), "资金活跃度", "neutral"),
            ("换手率", _pct(quote.get("turnover_rate")), "筹码交换", "watch"),
            ("PE/PB", f"{quote.get('pe') or '-'} / {quote.get('pb') or '-'}", "估值快照", "neutral"),
        ]
    )
    status_html = "".join(badge(f"{name}: {value}", _status_tone(value)) for name, value in _source_status(snapshot))
    st.markdown(
        "<div class='decision-card'>"
        f"{badge('数据已加载', 'buy')}"
        f"{badge('日K/周K/5日/分时', 'neutral')}"
        f"{status_html}"
        f"<div class='mini-note'>点击“刷新数据”可以强制重拉行情；分析按钮会按步骤展示正在执行的任务。</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    daily = snapshot["daily"]
    weekly = snapshot["weekly"]
    recent_5d = snapshot["recent_5d"]
    intraday = snapshot["intraday"]
    if not daily.empty:
        latest_close = float(daily.iloc[-1]["close"])
        high_60 = float(daily.tail(60)["high"].max())
        low_60 = float(daily.tail(60)["low"].min())
        render_insight(
            "价格位置速览",
            f"最新收盘 {latest_close:.2f}，近 60 日区间约 {low_60:.2f} - {high_60:.2f}。如果价格接近区间上沿，追高风险会增加；接近下沿时需要确认是否是风险释放而不是趋势破位。",
            "watch",
        )

    chart_range = st.radio("图表周期", ["日 K", "周 K", "近 5 日", "分时"], horizontal=True)
    chart_tabs = st.tabs(["行情图", "数据表"])
    with chart_tabs[0]:
        if chart_range == "日 K":
            if daily.empty:
                st.warning("暂无日线数据。")
            else:
                view = st.radio("日 K 视图", ["K 线", "价格 + 成交额"], horizontal=True)
                chart = _candlestick(daily, "日 K 与均线") if view == "K 线" else _price_amount_chart(daily.tail(120), "收盘价与成交额")
                st.plotly_chart(chart, width="stretch", key=f"detail_primary_{chart_range}_{view}")
        elif chart_range == "周 K":
            if weekly.empty:
                st.warning("暂无周线数据。")
            else:
                st.plotly_chart(_candlestick(weekly, "周 K 与均线"), width="stretch", key="detail_primary_weekly")
        elif chart_range == "近 5 日":
            if recent_5d.empty:
                st.warning("暂无近 5 日数据。")
            else:
                st.plotly_chart(_line(recent_5d, "date", "close", "近 5 日收盘走势"), width="stretch", key="detail_primary_5d")
        else:
            if intraday.empty:
                st.info("当前数据源没有返回分时数据，可能是非交易时段或接口暂不可用。")
            else:
                st.plotly_chart(_line(intraday, "time", "price", "当日分时走势"), width="stretch", key="detail_primary_intraday")
    with chart_tabs[1]:
        table = {"日 K": daily.tail(60), "周 K": weekly.tail(60), "近 5 日": recent_5d, "分时": intraday.tail(240)}[chart_range]
        st.dataframe(table, width="stretch", hide_index=True) if not table.empty else st.info("暂无可展示数据。")
    st.caption("图表切换不会重新拉取数据；点击刷新数据会重新生成行情快照。")

    with st.expander("数据来源与行业环境", expanded=False):
        c1, c2 = st.columns([1, 1])
        with c1:
            st.write("本页数据状态")
            st.dataframe(pd.DataFrame(_source_status(snapshot), columns=["模块", "状态"]), width="stretch", hide_index=True)
        with c2:
            industry = snapshot.get("industry_board")
            if isinstance(industry, pd.DataFrame) and not industry.empty:
                st.write("行业板块前 10")
                st.dataframe(industry.head(10), width="stretch", hide_index=True)
            else:
                st.info("行业板块接口暂未返回数据。")

    with st.expander("查看完整周期面板", expanded=False):
        legacy_tabs = st.tabs(["日 K", "周 K", "近 5 日", "分时"])
        with legacy_tabs[0]:
            st.plotly_chart(_candlestick(daily, "日 K 与均线"), width="stretch", key="detail_full_daily") if not daily.empty else st.warning("暂无日线数据。")
        with legacy_tabs[1]:
            st.plotly_chart(_candlestick(weekly, "周 K 与均线"), width="stretch", key="detail_full_weekly") if not weekly.empty else st.warning("暂无周线数据。")
        with legacy_tabs[2]:
            st.plotly_chart(_line(recent_5d, "date", "close", "近 5 日收盘走势"), width="stretch", key="detail_full_5d") if not recent_5d.empty else st.warning("暂无近 5 日数据。")
        with legacy_tabs[3]:
            st.plotly_chart(_line(intraday, "time", "price", "当日分时走势"), width="stretch", key="detail_full_intraday") if not intraday.empty else st.info("当前数据源没有返回分时数据。")

    st.divider()
    st.subheader("一键分析")
    algorithms = algorithm_service.list_algorithms()
    algo_map = {f"{algo.name} - {algo.description}": algo.id for algo in algorithms}
    selected_algos = st.multiselect("参与分析的算法", list(algo_map.keys()), default=list(algo_map.keys()))
    st.caption("不选时会使用全部算法；建议先从 2-4 个视角开始，再逐步加到全量组合。")
    run_analysis = st.button("开始完整分析", type="primary", width="stretch")

    if run_analysis:
        progress = st.progress(0, text="准备分析上下文...")
        result_box = st.container()
        render_timeline(
            [
                ("行情与指标", "读取日 K、周 K、近 5 日和分时数据。"),
                ("新闻证据", "抓取新闻并做相关性、事件类型和可信度评分。"),
                ("规则信号", "综合技术面、基本面、消息面、风控和学习记忆。"),
                ("组合算法", "计算多算法投票、共识度、冲突惩罚和仓位倾向。"),
                ("LLM 上下文", "生成可审计的输入快照，供 Skill 复核。"),
            ]
        )
        try:
            progress.progress(15, text="更新行情和指标...")
            data_service.update_daily_data(code)
            technical = IndicatorService().calculate(code)
            st.toast("行情与指标已更新")

            progress.progress(35, text="抓取并评分新闻证据...")
            news = NewsIngestionService().collect_for_stock(code, stock_name, limit=20)
            st.toast(f"新闻证据已评分：{len(news)} 条")

            progress.progress(55, text="运行规则信号...")
            signal = SignalService().analyze_stock(code, stock_name)
            st.toast("规则信号已生成")

            progress.progress(75, text="运行组合算法...")
            selected_ids = [algo_map[label] for label in selected_algos]
            algorithm_result = algorithm_service.run(code, stock_name, selected_ids, fetch_data=False)
            st.toast("组合算法已完成")

            progress.progress(90, text="构建 LLM Skill 上下文快照...")
            context = skill_service.build_computed_context(code, stock_name)
            progress.progress(100, text="分析完成")

            with result_box:
                st.success("完整分析已完成。")
                st.markdown(
                    "<div class='decision-card'>"
                    f"{badge(signal['action'], action_tone(signal['action']))}"
                    f"{badge(algorithm_result['action'], action_tone(algorithm_result['action']))}"
                    f"<div class='mini-note'>信号与组合算法同时给出，优先看风险点、失效条件和仓位建议。</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("信号动作", signal["action"])
                c2.metric("综合评分", f"{signal['overall_score']:.1f}")
                c3.metric("算法动作", algorithm_result["action"])
                c4.metric("新闻证据", len(news))
                st.info(algorithm_result["summary"])
                tabs = st.tabs(["信号", "组合算法", "技术指标", "LLM 上下文"])
                with tabs[0]:
                    st.write(signal["reason"])
                    st.json(signal)
                with tabs[1]:
                    combo = algorithm_result.get("combination", {})
                    combo_cols = st.columns(5)
                    combo_cols[0].metric("建议仓位", combo.get("position", "0%"))
                    combo_cols[1].metric("共识度", "-" if "consensus" not in combo else f"{combo['consensus']:.0%}")
                    combo_cols[2].metric("看多", combo.get("bullish_votes", 0))
                    combo_cols[3].metric("看空", combo.get("bearish_votes", 0))
                    combo_cols[4].metric("记忆惩罚", f"{combo.get('memory_penalty', 0):.1f}")
                    st.write(combo.get("notes", []))
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "算法": item["name"],
                                    "评分": item["score"],
                                    "方向": item.get("direction"),
                                    "仓位倾向": f"{item.get('position_bias', 0):.0%}",
                                    "理由": "；".join(item.get("reasons", [])),
                                    "风险": "；".join(item.get("risks", [])),
                                }
                                for item in algorithm_result["results"]
                            ]
                        ),
                        width="stretch",
                        hide_index=True,
                    )
                with tabs[2]:
                    st.json(technical)
                with tabs[3]:
                    st.json(context)
        except Exception as exc:
            progress.empty()
            st.error(f"分析失败：{exc}")
else:
    st.info("输入股票代码后会自动读取名称、行情和图表。")
