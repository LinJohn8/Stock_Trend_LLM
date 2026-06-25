from __future__ import annotations

import pandas as pd
import streamlit as st

from database.db import init_db
from services.portfolio_service import PortfolioService
from services.signal_service import SignalService
from services.stock_data_service import StockDataService

st.set_page_config(page_title="自选股管理", layout="wide")
init_db()
service = PortfolioService()

st.title("自选股管理")

with st.form("add_watchlist"):
    cols = st.columns([1, 1, 1, 2])
    code = cols[0].text_input("股票代码", placeholder="600519")
    name = cols[1].text_input("股票名称", placeholder="贵州茅台")
    industry = cols[2].text_input("行业", placeholder="白酒")
    tags = cols[3].text_input("标签", placeholder="长期关注,行业龙头")
    note = st.text_area("备注")
    submitted = st.form_submit_button("添加 / 更新")
    if submitted:
        try:
            service.add_watchlist(code, name, industry, note, tags)
            st.success("已保存自选股。")
        except Exception as exc:
            st.error(f"保存失败：{exc}")

items = service.list_watchlist()
st.subheader("自选股列表")
if items:
    st.dataframe(
        pd.DataFrame(
            [
                {"代码": x.stock_code, "名称": x.stock_name, "市场": x.market, "行业": x.industry, "标签": x.tags, "状态": "跟踪" if x.is_active else "暂停", "备注": x.note}
                for x in items
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
    selected = st.selectbox("选择操作股票", [x.stock_code for x in items])
    cols = st.columns(4)
    if cols[0].button("手动更新数据"):
        rows = StockDataService().update_daily_data(selected)
        st.success(f"已更新 {rows} 行日线数据。")
    if cols[1].button("手动分析"):
        item = next(x for x in items if x.stock_code == selected)
        signal = SignalService().analyze_stock(item.stock_code, item.stock_name)
        st.json(signal)
    if cols[2].button("暂停跟踪"):
        service.deactivate_watchlist(selected)
        st.success("已暂停。")
    if cols[3].button("删除"):
        service.delete_watchlist(selected)
        st.success("已删除。")
else:
    st.info("暂无自选股。")
