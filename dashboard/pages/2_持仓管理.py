from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from database.db import init_db
from services.holding_service import HoldingService
from services.signal_service import SignalService

st.set_page_config(page_title="持仓管理", layout="wide")
init_db()
service = HoldingService()

st.title("持仓管理")

with st.form("add_holding"):
    c1, c2, c3, c4 = st.columns(4)
    code = c1.text_input("股票代码", placeholder="300750")
    name = c2.text_input("股票名称", placeholder="宁德时代")
    buy_date = c3.date_input("买入日期", value=date.today())
    buy_time = c4.text_input("买入时间", value="09:30")
    c5, c6, c7, c8 = st.columns(4)
    buy_price = c5.number_input("买入价格", min_value=0.0, value=10.0, step=0.01)
    quantity = c6.number_input("买入数量", min_value=1, value=100, step=100)
    fee = c7.number_input("手续费", min_value=0.0, value=0.0, step=0.01)
    is_real = c8.checkbox("真实持仓", value=True)
    buy_reason = st.text_area("买入理由")
    source_info = st.text_area("当时参考信息")
    note = st.text_input("备注")
    submitted = st.form_submit_button("添加持仓")
    if submitted:
        try:
            service.add_holding(code, name, buy_date, service.parse_time(buy_time), buy_price, int(quantity), fee, buy_reason, source_info, is_real, note)
            st.success("持仓已添加。")
        except Exception as exc:
            st.error(f"添加失败：{exc}")

holdings = service.list_holdings()
st.subheader("持仓列表")
if holdings:
    rows = []
    for h in holdings:
        snap = service.snapshot_holding(h) if h.status != "sold" else None
        rows.append(
            {
                "ID": h.id,
                "代码": h.stock_code,
                "名称": h.stock_name,
                "买入日": h.buy_date,
                "买入价": h.buy_price,
                "当前数量": h.current_quantity,
                "总成本": h.total_cost,
                "当前价": None if not snap else snap.current_price,
                "市值": None if not snap else snap.market_value,
                "浮盈亏": None if not snap else snap.profit_amount,
                "浮盈亏率": None if not snap else f"{snap.profit_rate:.2%}",
                "持仓天数": None if not snap else snap.holding_days,
                "风险": None if not snap else snap.risk_level,
                "状态": h.status,
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    selected = st.selectbox("选择持仓 ID", [h.id for h in holdings])
    holding = next(h for h in holdings if h.id == selected)
    c1, c2, c3 = st.columns(3)
    if c1.button("分析该持仓"):
        snap = service.snapshot_holding(holding)
        signal = SignalService().analyze_stock(holding.stock_code, holding.stock_name, True, snap.profit_rate if snap else None)
        st.json(signal)
    if c2.button("标记已卖出"):
        service.mark_sold(selected)
        st.success("已标记卖出。")
    if c3.button("删除持仓"):
        service.delete_holding(selected)
        st.success("已删除。")
else:
    st.info("暂无持仓。")
