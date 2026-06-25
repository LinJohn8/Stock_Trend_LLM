from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from database.db import init_db
from services.memory_service import MemoryService

st.set_page_config(page_title="学习记忆", layout="wide")
init_db()
service = MemoryService()


def _load_json(value: str):
    try:
        return json.loads(value)
    except Exception:
        return value


st.title("学习记忆")
st.caption("把模拟建议的现实表现、失败原因、证据快照和后续规则修改建议结构化记录下来，供之后更新项目时复盘使用。")

cols = st.columns(4)
if cols[0].button("生成失败记忆", use_container_width=True):
    count = service.generate_learning_memories(include_success=False)
    st.success(f"已生成/更新 {count} 条失败或不确定记忆。")
if cols[1].button("生成全部记忆", use_container_width=True):
    count = service.generate_learning_memories(include_success=True)
    st.success(f"已生成/更新 {count} 条全部结果记忆。")

stats = service.stats()
cols[2].metric("记忆总数", stats["total"])
cols[3].metric("待处理", stats["open"])

status_filter = st.selectbox("状态筛选", ["全部", "open", "reviewed", "applied", "ignored"], index=0)
memories = service.list_memories(None if status_filter == "全部" else status_filter)

if memories:
    rows = []
    for item in memories:
        rows.append(
            {
                "ID": item.id,
                "股票": f"{item.stock_code} {item.stock_name}",
                "信号日": item.signal_date,
                "复盘日": item.review_date,
                "周期": f"{item.horizon_days}日",
                "原动作": item.original_action,
                "置信度": round(item.confidence, 0),
                "实际收益": None if item.actual_return is None else f"{item.actual_return:.2%}",
                "最大回撤": None if item.max_drawdown is None else f"{item.max_drawdown:.2%}",
                "结果": item.outcome,
                "错误类型": item.error_type,
                "状态": item.status,
                "经验": item.lesson,
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    selected_id = st.selectbox("查看/处理记忆 ID", [item.id for item in memories])
    selected = next(item for item in memories if item.id == selected_id)
    left, right = st.columns([1, 1])
    with left:
        st.subheader("可能原因")
        st.write(_load_json(selected.possible_causes))
        st.subheader("建议修改")
        st.write(_load_json(selected.proposed_changes))
    with right:
        st.subheader("证据快照")
        st.json(_load_json(selected.evidence_snapshot))

    status_cols = st.columns(4)
    for status, col in zip(["reviewed", "applied", "ignored", "open"], status_cols):
        if col.button(f"标记 {status}", use_container_width=True):
            service.mark_status(selected_id, status)
            st.success(f"已标记为 {status}。")
else:
    st.info("暂无学习记忆。先运行模拟复盘追踪，等信号有 1/5/20/60 日后表现后再生成。")
