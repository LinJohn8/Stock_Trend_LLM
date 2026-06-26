from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from dashboard.ui import inject_global_style
from database.db import init_db
from services.llm_skill_service import LLMReviewSkillService

st.set_page_config(page_title="LLM Skill 查看", layout="wide")
init_db()
inject_global_style()
service = LLMReviewSkillService()

st.title("LLM Skill 查看")
st.caption("先读取系统已经计算好的行情、指标、风险、信号、持仓和学习记忆，再选择一个 LLM Skill 做不同视角的解释。")

skills = service.list_skills()
skill_options = {"不使用 Skill，只查看计算结果": None}
skill_options.update({skill.name: skill.id for skill in skills})

left, right = st.columns([1, 1])
with left:
    stock_code = st.text_input("股票代码", value="600519")
    stock_name = st.text_input("股票名称", value="")
    selected_label = st.selectbox("选择查看方式", list(skill_options.keys()))
    selected_skill = skill_options[selected_label]
with right:
    st.subheader("可用 Skill")
    st.dataframe(
        pd.DataFrame([{"Skill": item.name, "ID": item.id, "用途": item.description} for item in skills]),
        width="stretch",
        hide_index=True,
    )

if stock_code:
    if selected_skill is None:
        if st.button("查看计算结果快照", width="stretch"):
            with st.spinner("正在读取计算结果..."):
                context = service.build_computed_context(stock_code, stock_name)
            st.subheader("计算结果快照")
            st.json(context)
    else:
        if st.button("运行所选 Skill 并保存", width="stretch"):
            with st.spinner("正在运行 LLM Skill..."):
                review = service.run_skill(stock_code, selected_skill, stock_name)
            st.success(f"已保存 Skill Review #{review.id}")
            st.markdown(review.result_text)

st.subheader("历史 Skill 查看记录")
reviews = service.list_reviews(stock_code if stock_code else None, limit=50)
if reviews:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": item.id,
                    "日期": item.review_date,
                    "股票": f"{item.stock_code} {item.stock_name}",
                    "Skill": item.skill_name,
                    "Provider": item.ai_provider,
                    "Model": item.ai_model,
                    "摘要": item.result_text[:120],
                }
                for item in reviews
            ]
        ),
        width="stretch",
        hide_index=True,
    )
    selected_review_id = st.selectbox("查看历史记录 ID", [item.id for item in reviews])
    selected_review = next(item for item in reviews if item.id == selected_review_id)
    tabs = st.tabs(["LLM 输出", "输入快照"])
    with tabs[0]:
        st.markdown(selected_review.result_text)
    with tabs[1]:
        try:
            st.json(json.loads(selected_review.input_snapshot))
        except Exception:
            st.code(selected_review.input_snapshot)
else:
    st.info("暂无 Skill 查看记录。")
