from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from database.db import init_db, session_scope
from database.models import AISignal, SignalTracking
from services.backtest_service import BacktestService
from services.memory_service import MemoryService

st.set_page_config(page_title="模拟交易复盘", layout="wide")
init_db()

st.title("模拟交易复盘")
service = BacktestService()
if st.button("更新未来收益追踪"):
    st.success(f"已更新 {service.update_tracking()} 条。")
if st.button("更新追踪并生成失败记忆"):
    result = service.update_tracking_and_memory(include_success=False)
    st.success(f"追踪更新 {result['tracked']} 条，学习记忆更新 {result['memories']} 条。")

stats = service.stats()
memory_stats = MemoryService().stats()
cols = st.columns(4)
cols[0].metric("总建议数", stats["total_signals"])
cols[1].metric("追踪数", stats["tracked_count"])
cols[2].metric("20日平均收益", "-" if stats["avg_return_20d"] is None else f"{stats['avg_return_20d']:.2%}")
cols[3].metric("失败记忆", memory_stats["open"])

with session_scope() as session:
    signals = list(session.scalars(select(AISignal)).all())
    tracks = list(session.scalars(select(SignalTracking)).all())
signal_map = {s.id: s for s in signals}
rows = []
for t in tracks:
    s = signal_map.get(t.signal_id)
    rows.append(
        {
            "日期": t.signal_date,
            "代码": t.stock_code,
            "动作": None if not s else s.action,
            "置信度": None if not s else s.confidence,
            "信号价格": t.price_at_signal,
            "1日": None if t.return_1d is None else f"{t.return_1d:.2%}",
            "5日": None if t.return_5d is None else f"{t.return_5d:.2%}",
            "20日": None if t.return_20d is None else f"{t.return_20d:.2%}",
            "60日": None if t.return_60d is None else f"{t.return_60d:.2%}",
            "最大回撤": None if t.max_drawdown_after_signal is None else f"{t.max_drawdown_after_signal:.2%}",
            "成功": t.is_success,
        }
    )
if rows:
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("暂无可复盘建议。")
