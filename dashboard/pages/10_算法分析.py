from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from database.db import init_db
from services.algorithm_service import AlgorithmService
from services.stock_data_service import StockDataService

st.set_page_config(page_title="算法分析", layout="wide")
init_db()
service = AlgorithmService()

st.title("算法分析")
st.caption("输入股票代码后先拉取/更新数据，再选择一个或多个确定性算法运行。LLM Skill 可以在算法结果之后再做解释。")

algorithms = service.list_algorithms()
algo_map = {f"{algo.name} - {algo.description}": algo.id for algo in algorithms}

with st.form("algorithm_form"):
    c1, c2, c3 = st.columns([1, 1, 1])
    stock_code = c1.text_input("股票代码", value="600519")
    stock_name = c2.text_input("股票名称", value="")
    fetch_data = c3.checkbox("运行前拉取/更新数据", value=True)
    selected_labels = st.multiselect("选择算法", list(algo_map.keys()), default=list(algo_map.keys()))
    submitted = st.form_submit_button("运行算法分析")

if submitted:
    selected_ids = [algo_map[label] for label in selected_labels]
    if not selected_ids:
        st.error("请至少选择一个算法。")
    else:
        with st.spinner("正在拉取数据并运行算法..."):
            result = service.run(stock_code, stock_name, selected_ids, fetch_data=fetch_data)
        st.success("算法分析完成。")
        c1, c2, c3 = st.columns(3)
        c1.metric("综合评分", f"{result['overall_score']:.1f}")
        c2.metric("动作", result["action"])
        c3.metric("置信度", f"{result['confidence']:.0f}/100")
        st.info(result["summary"])
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "算法": item["name"],
                        "评分": round(item["score"], 1),
                        "视角": item["view"],
                        "理由": "；".join(item.get("reasons", [])),
                        "风险": "；".join(item.get("risks", [])),
                    }
                    for item in result["results"]
                ]
            ),
            use_container_width=True,
            hide_index=True,
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
        use_container_width=True,
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
