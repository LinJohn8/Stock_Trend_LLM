from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.ui import (
    action_tone,
    apply_chart_interaction,
    badge,
    inject_global_style,
    render_copy_button,
    render_hero,
    render_kpi_grid,
    render_loading_panel,
    render_static_table,
)
from database.db import init_db
from services.stock_screening_service import ScreeningConfig, StockScreeningService

st.set_page_config(page_title="选股模拟", layout="wide")
init_db()
inject_global_style()

render_hero(
    "选股模拟 + 分析入口",
    "输入可用资金后，先过滤一手可以买入的股票，再用实时行情、流动性、估值和日线结构做可解释排序。点击结果即可进入股票工作台做新闻、算法、AI 深度分析。",
    "Affordable Stock Radar",
    [("真实行情过滤", "buy"), ("一手成本约束", "watch"), ("跳转深度分析", "neutral")],
)

service = StockScreeningService()

with st.form("screening_form"):
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    cash = c1.number_input("可用资金", min_value=100, max_value=10_000_000, value=1000, step=100, help="A 股通常一手 100 股。1000 元会优先找价格不高于 10 元的股票。")
    max_candidates = c2.slider("候选数量上限", 20, 200, 80, 10, help="先从全市场实时表中按成交额筛出一批可买候选。")
    enrich_top = c3.slider("深度补充数量", 0, 60, 24, 4, help="对前 N 只补充日线趋势评分。数量越大越慢，但排序更稳。")
    min_amount_yi = c4.number_input("最低成交额(亿)", min_value=0.0, max_value=50.0, value=0.0, step=0.1, help="可过滤过于冷清的低价股。")
    c5, c6 = st.columns([1, 3])
    exclude_st = c5.checkbox("排除 ST", value=True)
    c6.caption("说明：本页用于发现候选，不等于买入建议。进入工作台后还需要看新闻、公告、历史走势、算法冲突和资金限制。")
    submitted = st.form_submit_button("开始选股模拟", type="primary")

if submitted:
    with st.spinner("正在获取全市场实时行情并筛选一手可买股票..."):
        render_loading_panel("选股扫描中", "正在读取实时行情表、过滤价格、计算流动性/估值/趋势评分。")
        st.session_state["screening_result"] = service.screen_affordable(
            ScreeningConfig(
                cash=float(cash),
                max_candidates=int(max_candidates),
                enrich_top=int(enrich_top),
                exclude_st=exclude_st,
                min_amount=float(min_amount_yi) * 100_000_000,
            )
        )

result = st.session_state.get("screening_result")
if not result:
    st.info("输入资金后点击“开始选股模拟”。例如 1000 元会筛选当前价格不高于 10 元、理论上一手可买的股票。")
    st.stop()

rows = result.get("results", [])
render_kpi_grid(
    [
        ("可用资金", f"{float(result['cash']):,.0f}", "用户输入资金", "neutral"),
        ("价格上限", f"{float(result['one_lot_price_limit']):.2f}", "一手 100 股约束", "watch"),
        ("全市场行数", str(result.get("total_rows", 0)), f"来源 {result.get('source', '-')}", "neutral"),
        ("可买候选", str(result.get("affordable_rows", 0)), "过滤后一手可买", "buy" if rows else "risk"),
    ]
)

if result.get("diagnostics"):
    st.warning("；".join(result["diagnostics"][:6]))

if not rows:
    st.error("没有筛到符合资金约束的候选。可以提高资金、降低最低成交额，或稍后重试行情源。")
    st.stop()

copy_text = "\n".join(
    [
        "# 选股模拟结果",
        f"资金：{result['cash']}，一手价格上限：{result['one_lot_price_limit']:.2f}",
        "",
        *[
            (
                f"{idx}. {item['stock_code']} {item['stock_name']} | 价格 {item['current_price']} | "
                f"一手成本 {item['one_lot_cost']:.2f} | 评分 {item['score']} | 动作 {item['action']} | "
                f"理由：{'；'.join(item['reasons'])} | 风险：{'；'.join(item['risks'])}"
            )
            for idx, item in enumerate(rows[:40], start=1)
        ],
    ]
)
render_copy_button("复制选股结果", copy_text, "screening_copy_result", "复制候选、评分、理由和风险")

st.subheader("推荐排序")
left, right = st.columns([1.55, 1], gap="large")
with left:
    display_rows = []
    for idx, item in enumerate(rows, start=1):
        display_rows.append(
            {
                "排名": idx,
                "代码": item["stock_code"],
                "名称": item["stock_name"],
                "价格": f"{item['current_price']:.2f}",
                "一手成本": f"{item['one_lot_cost']:.0f}",
                "涨跌幅": "-" if item.get("pct_change") is None else f"{item['pct_change']:.2f}%",
                "成交额(亿)": "-" if item.get("amount") is None else f"{item['amount'] / 100000000:.2f}",
                "评分": item["score"],
                "置信度": item["confidence"],
                "动作": item["action"],
                "主要理由": "；".join(item["reasons"][:2]),
                "主要风险": "；".join(item["risks"][:2]),
            }
        )
    render_static_table(display_rows, ["排名", "代码", "名称", "价格", "一手成本", "涨跌幅", "成交额(亿)", "评分", "置信度", "动作", "主要理由", "主要风险"], max_cell_length=180)

with right:
    st.markdown("<div class='chat-panel'><strong>下一步深度分析</strong><div class='mini-note'>选择一只股票后，会把代码和名称写入工作台状态。进入工作台点击“一键全流程分析”即可继续抓新闻、跑算法并问 AI。</div></div>", unsafe_allow_html=True)
    option_labels = [f"{item['stock_code']} {item['stock_name']} | 分 {item['score']} | {item['action']}" for item in rows[:80]]
    selected_label = st.selectbox("选择进入工作台的股票", option_labels)
    selected_index = option_labels.index(selected_label)
    selected = rows[selected_index]
    st.markdown(
        "<div class='decision-card'>"
        f"{badge(selected['action'], action_tone(selected['action']))}"
        f"<div><strong>{selected['stock_code']} {selected['stock_name']}</strong></div>"
        f"<div class='mini-note'>价格 {selected['current_price']:.2f}，一手成本 {selected['one_lot_cost']:.2f}，评分 {selected['score']}。</div>"
        f"<div class='mini-note'>理由：{'；'.join(selected['reasons'])}</div>"
        f"<div class='mini-note'>风险：{'；'.join(selected['risks'])}</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    if st.button("写入工作台并打开深度分析页", type="primary", width="stretch"):
        st.session_state["workbench_code"] = selected["stock_code"]
        st.session_state["workbench_name"] = selected["stock_name"]
        st.session_state["workbench_from_screening"] = {
            "cash": result["cash"],
            "one_lot_price_limit": result["one_lot_price_limit"],
            "rank": selected_index + 1,
            "score": selected["score"],
            "reasons": selected["reasons"],
            "risks": selected["risks"],
        }
        try:
            st.switch_page("pages/12_股票工作台.py")
        except Exception:
            st.success("已写入工作台状态。请从左侧页面切到“股票工作台”。")

st.subheader("评分分布")
chart_df = pd.DataFrame(rows[:80])
if not chart_df.empty:
    chart_df["标签"] = chart_df["stock_code"] + " " + chart_df["stock_name"]
    fig = px.bar(
        chart_df,
        x="标签",
        y="score",
        color="action",
        color_discrete_map={"buy_candidate": "#1a6f55", "watch": "#a06a16", "uncertain": "#285f86", "avoid": "#a23d31"},
        hover_data=["current_price", "one_lot_cost", "confidence", "amount"],
        title="候选评分分布",
    )
    st.plotly_chart(apply_chart_interaction(fig, y_title="评分", x_title="候选股票"), width="stretch", key="screening_score_chart")
