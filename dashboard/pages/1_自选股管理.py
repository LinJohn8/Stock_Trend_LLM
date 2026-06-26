from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.ui import action_tone, apply_chart_interaction, badge, inject_global_style, render_loading_panel, render_static_table
from database.db import init_db
from services.portfolio_service import PortfolioService
from services.signal_service import SignalService
from services.stock_data_service import StockDataService

st.set_page_config(page_title="自选股管理", layout="wide")
init_db()
inject_global_style()

portfolio = PortfolioService()
stock_service = StockDataService()

st.title("自选股管理")
st.caption("默认只读取本地自选股，避免打开页面就卡。需要行情、图表或分析时再点击按钮触发。")


def _rows(items) -> list[dict]:
    return [
        {
            "代码": item.stock_code,
            "名称": item.stock_name,
            "市场": item.market,
            "行业": item.industry,
            "标签": item.tags,
            "状态": "启用" if item.is_active else "暂停",
            "备注": item.note,
        }
        for item in items
    ]


items = portfolio.list_watchlist()
code_options = [item.stock_code for item in items]
item_map = {item.stock_code: item for item in items}

with st.container():
    c1, c2, c3 = st.columns([1, 1, 2])
    quick_code = c1.text_input("股票代码", value=st.session_state.get("watchlist_edit_code", ""), placeholder="600519")
    if c2.button("识别名称/价格", width="stretch", disabled=not quick_code):
        with st.spinner("正在识别股票信息..."):
            quote = stock_service.resolve_stock_profile(quick_code)
        st.session_state["watchlist_detected_quote"] = quote
        st.toast(f"识别完成：{quote['display_name']}")
    quote = st.session_state.get("watchlist_detected_quote")
    if quote:
        c3.markdown(
            "<div class='decision-card'>"
            f"{badge(quote['display_name'], 'neutral')}"
            f"{badge(quote.get('source', 'unknown'), 'buy')}"
            f"<div class='mini-note'>最新价 {quote.get('current_price') or '-'}，涨跌幅 {quote.get('pct_change') if quote.get('pct_change') is not None else '-'}%。</div>"
            "</div>",
            unsafe_allow_html=True,
        )

tabs = st.tabs(["本地列表", "新增/编辑", "查看与分析"])

with tabs[0]:
    if items:
        render_static_table(_rows(items), ["代码", "名称", "市场", "行业", "标签", "状态", "备注"])
        st.caption("这个表格是普通自适应表格，不启用 Notion 式拖拽/组合交互。")
        with st.expander("批量删除", expanded=False):
            selected_codes = st.multiselect("选择要删除的自选股", code_options, format_func=lambda code: f"{code} {item_map[code].stock_name}")
            confirmed = st.checkbox(f"确认删除 {len(selected_codes)} 条自选股", disabled=not selected_codes)
            if st.button("批量删除自选股", type="primary", disabled=not selected_codes or not confirmed):
                deleted = portfolio.delete_watchlist_many(selected_codes)
                st.success(f"已删除 {deleted} 条自选股。")
                st.rerun()
    else:
        st.info("暂无自选股。可以在“新增/编辑”里添加。")

with tabs[1]:
    edit_code = st.selectbox("选择已有股票编辑，或留空新增", [""] + code_options)
    default = item_map.get(edit_code)
    detected = st.session_state.get("watchlist_detected_quote") or {}
    with st.form("watchlist_crud_form", clear_on_submit=False):
        c1, c2, c3 = st.columns([1, 1, 1])
        code = c1.text_input("股票代码", value=default.stock_code if default else quick_code)
        name = c2.text_input("股票名称", value=default.stock_name if default else detected.get("stock_name", ""))
        industry = c3.text_input("行业", value=default.industry if default else "")
        c4, c5 = st.columns([2, 1])
        note = c4.text_input("备注", value=default.note if default else "")
        tags = c5.text_input("标签", value=default.tags if default else "")
        active = st.checkbox("启用跟踪", value=True if default is None else default.is_active)
        submitted = st.form_submit_button("保存自选股", type="primary")
    if submitted:
        try:
            resolved_name = name
            if not resolved_name:
                with st.spinner("名称为空，正在自动识别..."):
                    resolved_name = stock_service.resolve_stock_profile(code).get("stock_name", "")
            saved = portfolio.update_watchlist(code, resolved_name, industry, note, tags, active)
            if not saved:
                saved = portfolio.add_watchlist(code, resolved_name, industry, note, tags)
                if not active:
                    portfolio.update_watchlist(code, is_active=False)
            st.success(f"已保存：{saved.stock_code} {saved.stock_name}")
            st.rerun()
        except Exception as exc:
            st.error(f"保存失败：{exc}")

with tabs[2]:
    if not items:
        st.info("暂无可查看的自选股。")
    else:
        selected_code = st.selectbox("选择自选股", code_options, format_func=lambda code: f"{code} {item_map[code].stock_name}")
        selected = item_map[selected_code]
        actions = st.columns(5)
        if actions[0].button("查看行情", width="stretch"):
            with st.spinner("正在读取行情和图表..."):
                render_loading_panel("读取行情", "正在获取最新报价、日线和均线。")
                st.session_state["watchlist_snapshot"] = stock_service.get_market_snapshot(selected_code)
                st.session_state["watchlist_snapshot_code"] = selected_code
        if actions[1].button("运行分析", width="stretch"):
            with st.spinner("正在运行规则分析..."):
                st.session_state["watchlist_signal"] = SignalService().analyze_stock(selected_code, selected.stock_name)
                st.session_state["watchlist_signal_code"] = selected_code
        if actions[2].button("暂停/恢复", width="stretch"):
            portfolio.update_watchlist(selected_code, is_active=not selected.is_active)
            st.success("状态已更新。")
            st.rerun()
        if actions[3].button("填入编辑", width="stretch"):
            st.session_state["watchlist_edit_code"] = selected_code
            st.info("已填入顶部代码框，可切换到“新增/编辑”修改。")
        if actions[4].button("删除", width="stretch"):
            deleted = portfolio.delete_watchlist(selected_code)
            st.success("已删除。" if deleted else "该自选股已不存在。")
            st.rerun()

        snapshot = st.session_state.get("watchlist_snapshot")
        if snapshot and st.session_state.get("watchlist_snapshot_code") == selected_code:
            quote = snapshot["quote"]
            display_name = f"{quote['stock_code']} {quote.get('stock_name') or selected.stock_name}"
            latest_label = f"最新 {quote.get('current_price') or '-'}"
            pct_label = f"涨跌幅 {quote.get('pct_change') if quote.get('pct_change') is not None else '-'}%"
            st.markdown(
                "<div class='decision-card'>"
                f"{badge(display_name, 'neutral')}"
                f"{badge(latest_label, 'buy')}"
                f"{badge(pct_label, 'watch')}"
                "</div>",
                unsafe_allow_html=True,
            )
            daily = snapshot["daily"].tail(90)
            if not daily.empty:
                chart_df = daily.copy()
                chart_df["MA5"] = chart_df["close"].rolling(5).mean()
                chart_df["MA20"] = chart_df["close"].rolling(20).mean()
                fig = px.line(chart_df, x="date", y=["close", "MA5", "MA20"], title="价格与均线")
                fig.update_traces(hovertemplate="%{x}<br>%{fullData.name} %{y:.2f}<extra></extra>")
                st.plotly_chart(apply_chart_interaction(fig, y_title="价格", x_title="日期"), width="stretch", key="watchlist_view_price")
                render_static_table(daily.tail(20).to_dict("records"), ["date", "open", "high", "low", "close", "volume", "pct_change"])

        signal = st.session_state.get("watchlist_signal")
        if signal and st.session_state.get("watchlist_signal_code") == selected_code:
            score_label = f"评分 {signal['overall_score']:.1f}"
            st.markdown(
                "<div class='decision-card'>"
                f"{badge(signal['action'], action_tone(signal['action']))}"
                f"{badge(score_label, 'neutral')}"
                f"<div class='mini-note'>{signal['reason']}</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            render_static_table(
                [
                    {"项目": "建议仓位", "值": signal.get("suggested_position")},
                    {"项目": "止损价", "值": signal.get("stop_loss_price")},
                    {"项目": "止盈价", "值": signal.get("take_profit_price")},
                    {"项目": "风险点", "值": "；".join(signal.get("risk_points", []))},
                ]
            )
