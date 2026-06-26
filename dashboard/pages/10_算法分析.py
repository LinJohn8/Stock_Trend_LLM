from __future__ import annotations

import json

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.ui import action_tone, apply_chart_interaction, badge, inject_global_style, render_hero, render_insight, render_kpi_grid, render_static_table
from database.db import init_db
from services.algorithm_service import AlgorithmService
from services.stock_data_service import StockDataService

st.set_page_config(page_title="算法分析", layout="wide")
init_db()
inject_global_style()
service = AlgorithmService()

render_hero(
    "算法组合分析台",
    "选择单个算法或多算法组合。组合逻辑会综合方向投票、共识度、冲突惩罚、硬风控、学习记忆和仓位倾向，不是简单加权平均。",
    "Algorithm Matrix",
    [("可单选", "neutral"), ("可组合", "buy"), ("硬风控", "risk")],
)

algorithms = service.list_algorithms()
default_ids = set(service.default_algorithm_ids())
categories = ["全部"] + sorted({algo.category for algo in algorithms})
render_kpi_grid(
    [
        ("算法总数", str(len(algorithms)), "核心 + 参数化变体", "buy"),
        ("默认强算法", str(len(default_ids)), "未选择时使用", "neutral"),
        ("分类数", str(len(categories) - 1), "可按类别筛选", "watch"),
        ("组合逻辑", "非简单平均", "共识/冲突/风控/记忆", "risk"),
    ]
)

with st.form("algorithm_form"):
    c1, c2, c3 = st.columns([1, 1, 1])
    stock_code = c1.text_input("股票代码", value="600519")
    stock_name = c2.text_input("股票名称", value="")
    fetch_data = c3.checkbox("运行前拉取/更新数据", value=True)
    c4, c5, c6 = st.columns([1, 1, 1])
    category_filter = c4.selectbox("算法分类筛选", categories)
    selection_mode = c5.selectbox("默认选择", ["强核心算法", "当前分类全部", "手动空选"])
    max_display = c6.slider("列表显示上限", 20, 260, 120, step=20)
    visible_algorithms = algorithms if category_filter == "全部" else [algo for algo in algorithms if algo.category == category_filter]
    visible_algorithms = visible_algorithms[:max_display]
    algo_map = {
        f"[{algo.category}] {'★ ' if algo.default else ''}{algo.name} - {algo.description}": algo.id
        for algo in visible_algorithms
    }
    if selection_mode == "强核心算法":
        default_labels = [label for label, algo_id in algo_map.items() if algo_id in default_ids]
    elif selection_mode == "当前分类全部":
        default_labels = list(algo_map.keys())
    else:
        default_labels = []
    selected_labels = st.multiselect(
        "选择算法（可多选/少选；列表过多时先按分类筛选）",
        list(algo_map.keys()),
        default=default_labels,
        help="算法库包含数百个参数化算法。建议默认使用强核心算法，需要压力测试时再按分类批量加入。",
    )
    submitted = st.form_submit_button("运行算法分析")

if submitted:
    selected_ids = [algo_map[label] for label in selected_labels]
    if not selected_ids:
        st.error("请至少选择一个算法。")
    else:
        with st.spinner("正在拉取数据并运行算法..."):
            result = service.run(stock_code, stock_name, selected_ids, fetch_data=fetch_data)
        st.success("算法分析完成。")
        st.markdown(
            "<div class='decision-card'>"
            f"{badge(result['action'], action_tone(result['action']))}"
            f"<div class='mini-note'>{result['summary']}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        render_kpi_grid(
            [
                ("综合评分", f"{result['overall_score']:.1f}", "多算法调整后", action_tone(result["action"])),
                ("动作", result["action"], "最终建议动作", action_tone(result["action"])),
                ("置信度", f"{result['confidence']:.0f}/100", "共识与分歧修正", "neutral"),
            ]
        )
        combo = result.get("combination", {})
        render_kpi_grid(
            [
                ("建议仓位", combo.get("position", "0%"), "组合仓位倾向", "buy" if combo.get("position") not in {"0%", "0"} else "watch"),
                ("共识度", "-" if "consensus" not in combo else f"{combo['consensus']:.0%}", "方向一致性", "neutral"),
                ("看多票", str(combo.get("bullish_votes", 0)), "算法方向", "buy"),
                ("看空票", str(combo.get("bearish_votes", 0)), "风险方向", "risk" if combo.get("bearish_votes", 0) else "neutral"),
                ("冲突惩罚", f"{combo.get('conflict_penalty', 0):.1f}", "分歧扣分", "watch"),
            ]
        )
        if combo.get("notes"):
            render_insight("组合解释", "；".join(combo["notes"]), "watch")
        result_df = pd.DataFrame(
            [
                {
                    "算法": item["name"],
                    "分类": item.get("view", ""),
                    "评分": round(item["score"], 1),
                    "方向": item.get("direction", "neutral"),
                    "仓位倾向": item.get("position_bias", 0),
                    "理由": "；".join(item.get("reasons", [])),
                    "风险": "；".join(item.get("risks", [])),
                }
                for item in result["results"]
            ]
        )
        chart_cols = st.columns([1, 1])
        with chart_cols[0]:
            fig = px.bar(result_df, x="算法", y="评分", color="方向", title="算法评分与方向")
            st.plotly_chart(apply_chart_interaction(fig, y_title="评分", x_title="算法"), width="stretch", key="algorithm_score_bar")
        with chart_cols[1]:
            radar = go.Figure()
            radar.add_trace(
                go.Scatterpolar(
                    r=result_df["评分"].tolist() + [result_df["评分"].iloc[0]],
                    theta=result_df["算法"].tolist() + [result_df["算法"].iloc[0]],
                    fill="toself",
                    name="评分轮廓",
                )
            )
            radar.update_layout(title="算法评分雷达", height=430, polar=dict(radialaxis=dict(visible=True, range=[0, 100])))
            st.plotly_chart(apply_chart_interaction(radar, y_title="评分", x_title="算法"), width="stretch", key="algorithm_score_radar")
        render_static_table(
            result_df.assign(仓位倾向=lambda df: df["仓位倾向"].map(lambda value: f"{value:.0%}")).to_dict("records"),
            ["算法", "分类", "评分", "方向", "仓位倾向", "理由", "风险"],
            max_cell_length=220,
        )
        with st.expander("完整 JSON 结果"):
            st.json(result)

st.subheader("历史算法运行")
filter_code = st.text_input("按股票代码筛选历史", value="")
runs = service.list_runs(filter_code or None, limit=100)
if runs:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": item.id,
                    "日期": item.run_date,
                    "股票": f"{item.stock_code} {item.stock_name}",
                    "算法": ", ".join(json.loads(item.selected_algorithms)),
                    "综合": round(item.overall_score, 1),
                    "动作": item.action,
                    "置信度": round(item.confidence, 0),
                }
                for item in runs
            ]
        ),
        width="stretch",
        hide_index=True,
    )
    selected_id = st.selectbox("查看运行 ID", [item.id for item in runs])
    selected = next(item for item in runs if item.id == selected_id)
    st.json(json.loads(selected.result_json))
else:
    st.info("暂无算法运行记录。")

st.subheader("单独拉取数据")
pull_code = st.text_input("股票代码拉取", value="000001")
if st.button("拉取/更新日线数据"):
    rows = StockDataService().update_daily_data(pull_code)
    st.success(f"已更新 {rows} 行数据。")
