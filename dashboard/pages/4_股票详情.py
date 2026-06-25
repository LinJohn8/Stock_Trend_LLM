from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from database.db import init_db
from services.indicator_service import IndicatorService
from services.llm_skill_service import LLMReviewSkillService
from services.signal_service import SignalService
from services.stock_data_service import StockDataService

st.set_page_config(page_title="股票详情", layout="wide")
init_db()

st.title("股票详情")
code = st.text_input("输入股票代码", value="600519")
if code:
    data_service = StockDataService()
    skill_service = LLMReviewSkillService()
    if st.button("更新并分析"):
        data_service.update_daily_data(code)
        st.json(SignalService().analyze_stock(code))
    df = data_service.get_daily_dataframe(code, limit=180)
    if not df.empty:
        IndicatorService().calculate(code)
        df["ma5"] = df["close"].rolling(5).mean()
        df["ma20"] = df["close"].rolling(20).mean()
        df["ma60"] = df["close"].rolling(60).mean()
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.04)
        fig.add_trace(go.Candlestick(x=df["date"], open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="K线"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["date"], y=df["ma5"], name="MA5"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["date"], y=df["ma20"], name="MA20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["date"], y=df["ma60"], name="MA60"), row=1, col=1)
        fig.add_trace(go.Bar(x=df["date"], y=df["volume"], name="成交量"), row=2, col=1)
        fig.update_layout(height=640, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df.tail(30), use_container_width=True, hide_index=True)

        st.subheader("LLM Skill 查看")
        skills = skill_service.list_skills()
        options = {"不使用 Skill，只查看计算结果": None}
        options.update({skill.name: skill.id for skill in skills})
        selected = st.selectbox("选择 Skill", list(options.keys()))
        if st.button("运行查看"):
            if options[selected] is None:
                st.json(skill_service.build_computed_context(code))
            else:
                review = skill_service.run_skill(code, options[selected])
                st.success(f"已保存 Skill Review #{review.id}")
                st.markdown(review.result_text)
    else:
        st.warning("暂无行情数据，可能是网络、代码或数据源问题。")
