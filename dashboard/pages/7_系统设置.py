from __future__ import annotations

import streamlit as st

from config.settings import get_settings
from dashboard.ui import inject_global_style
from database.db import init_db

st.set_page_config(page_title="系统设置", layout="wide")
init_db()
inject_global_style()
settings = get_settings()

st.title("系统设置")
st.subheader("分析权重")
st.json(settings.score_weights)
st.subheader("风险阈值")
st.write(
    {
        "止损阈值": settings.stop_loss_threshold,
        "止盈提示阈值": settings.take_profit_threshold,
        "最大建议仓位": settings.max_suggested_position,
        "AI Provider": settings.ai_provider,
        "AI Enabled": settings.ai_enabled,
        "数据库": settings.database_url,
    }
)
st.info("第一版配置优先从 .env 读取；system_settings 表已建好，后续可把页面编辑值写入数据库并覆盖 .env。")
