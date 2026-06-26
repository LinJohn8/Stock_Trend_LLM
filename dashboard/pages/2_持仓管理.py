from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.ui import action_tone, apply_chart_interaction, badge, inject_global_style
from database.db import init_db
from services.holding_service import HoldingService
from services.signal_service import SignalService
from services.stock_data_service import StockDataService

st.set_page_config(page_title="持仓管理", layout="wide")
init_db()
inject_global_style()
service = HoldingService()
stock_service = StockDataService()

st.title("持仓管理")
st.caption("支持新增、编辑、分析、卖出和删除，并展示持仓快照和收益曲线。")

items = service.list_holdings()
holding_map = {f"{item.id} · {item.stock_code} {item.stock_name}": item for item in items}

tabs = st.tabs(["添加/编辑", "持仓列表", "持仓详情"])

with tabs[0]:
    chosen_label = st.selectbox("选择已有持仓编辑或新增", [""] + list(holding_map.keys()), index=0)
    default = holding_map.get(chosen_label)
    preview_code = st.text_input(
        "先输入股票代码自动识别",
        value=default.stock_code if default else "",
        key="holding_preview_code",
        help="这里用于预览股票名称、最新价格和数据来源；下方保存表单会同步使用该代码。",
    )
    preview_quote = None
    if preview_code:
        try:
            preview_quote = stock_service.resolve_stock_profile(preview_code)
            st.markdown(
                "<div class='decision-card'>"
                f"{badge(preview_quote['display_name'], 'neutral')}"
                f"{badge(preview_quote.get('source', 'unknown'), 'buy')}"
                f"<div class='mini-note'>最新价 {preview_quote.get('current_price') or '-'}，涨跌幅 {preview_quote.get('pct_change') if preview_quote.get('pct_change') is not None else '-'}%。</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        except Exception as exc:
            st.warning(f"暂时无法识别该代码：{exc}")
    with st.form("holding_form", clear_on_submit=False):
        c1, c2, c3, c4 = st.columns(4)
        code = c1.text_input("股票代码", value=preview_code or (default.stock_code if default else ""), help="A 股 6 位代码，例如 600519。保存时会自动标准化。")
        name = c2.text_input("股票名称", value=default.stock_name if default and default.stock_name else (preview_quote or {}).get("stock_name", ""), help="可手动修改；如果留空，系统会尽量用行情源识别。")
        buy_date = c3.date_input("买入日期", value=default.buy_date if default else date.today(), help="实际买入日期，用于计算持仓天数和复盘区间。")
        buy_time = c4.text_input("买入时间", value=default.buy_time.strftime("%H:%M") if default and default.buy_time else "09:30", help="格式 HH:MM，例如 09:30。用于记录当时决策，不参与自动交易。")
        c5, c6, c7, c8 = st.columns(4)
        buy_price = c5.number_input("买入价格", min_value=0.0, value=float(default.buy_price) if default else 10.0, step=0.01, help="实际成交均价。系统用它和当前价自动计算盈亏。")
        quantity = c6.number_input("买入数量", min_value=1, value=int(default.quantity) if default else 100, step=100, help="最初买入数量。A 股通常按 100 股一手。")
        current_quantity = c7.number_input("现在剩余数量", min_value=0, value=int(default.current_quantity) if default else int(quantity), step=100, help="当前还持有多少股；如果卖出了一部分，在这里修改。")
        fee = c8.number_input("手续费", min_value=0.0, value=float(default.fee) if default else 0.0, step=0.01, help="买入时的佣金/过户费等总成本，可填 0。")
        is_real = st.checkbox("真实持仓", value=True if default is None else bool(default.is_real_position), help="关闭后表示观察/模拟持仓，不会当成真实仓位看待。")
        buy_reason = st.text_area("买入理由", value=default.buy_reason if default else "", help="记录当时为什么买，后续复盘时非常关键。")
        source_info = st.text_area("当时参考信息", value=default.source_info if default else "", help="记录当时看过的新闻、公告、研报、技术形态或朋友建议，方便以后判断信息源质量。")
        note = st.text_input("备注", value=default.note if default else "", help="自由备注，例如计划止损位、目标位、仓位安排。")
        status = st.selectbox("状态", ["holding", "watching", "partially_sold", "sold"], index=["holding", "watching", "partially_sold", "sold"].index(default.status) if default else 0, help="holding=持有，watching=观察，partially_sold=部分卖出，sold=已清仓。")
        latest_price = None if not preview_quote else preview_quote.get("current_price")
        current_value = 0 if latest_price is None else latest_price * int(current_quantity)
        cost_basis = float(buy_price) * int(current_quantity) + float(fee)
        profit = None if latest_price is None else current_value - cost_basis
        profit_rate = None if latest_price is None or cost_basis <= 0 else profit / cost_basis
        st.markdown(
            "<div class='decision-card'>"
            f"<strong>保存前自动估算</strong>"
            f"<div class='mini-note'>成本基数：{cost_basis:,.2f}；当前市值：{current_value:,.2f}；浮盈亏：{'-' if profit is None else f'{profit:,.2f}'}；浮盈亏率：{'-' if profit_rate is None else f'{profit_rate:.2%}'}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        submitted = st.form_submit_button("保存持仓")
    if submitted:
        try:
            parsed_time = service.parse_time(buy_time)
            if default:
                saved = service.update_holding(
                    default.id,
                    stock_name=name,
                    buy_date=buy_date,
                    buy_time=parsed_time,
                    buy_price=float(buy_price),
                    quantity=int(quantity),
                    fee=float(fee),
                    buy_reason=buy_reason,
                    source_info=source_info,
                    is_real_position=is_real,
                    note=note,
                    status=status,
                )
                if saved and saved.current_quantity != int(current_quantity):
                    service.update_current_quantity(saved.id, int(current_quantity))
                st.success(f"已更新持仓 #{saved.id}。")
            else:
                resolved_name = name or (preview_quote or {}).get("stock_name", "")
                saved = service.add_holding(code, resolved_name, buy_date, parsed_time, float(buy_price), int(quantity), float(fee), buy_reason, source_info, is_real, note)
                if saved.current_quantity != int(current_quantity):
                    service.update_current_quantity(saved.id, int(current_quantity))
                st.success(f"已新增持仓 #{saved.id}。")
        except Exception as exc:
            st.error(f"保存失败：{exc}")

with tabs[1]:
    items = service.list_holdings()
    if items:
        rows = []
        for h in items:
            snap = service.value_holding(h) if h.status != "sold" else None
            rows.append(
                {
                    "ID": h.id,
                    "代码": h.stock_code,
                    "名称": h.stock_name,
                    "状态": h.status,
                    "买入价": h.buy_price,
                    "初始数量": h.quantity,
                    "剩余数量": h.current_quantity,
                    "成本": h.buy_price * h.current_quantity + h.fee,
                    "当前价": None if not snap else snap.current_price,
                    "当前市值": None if not snap else snap.market_value,
                    "浮盈亏": None if not snap else snap.profit_amount,
                    "浮盈亏率": None if not snap else f"{snap.profit_rate:.2%}",
                    "风险": None if not snap else snap.risk_level,
                    "备注": h.note,
                }
            )
        holdings_df = pd.DataFrame(rows)
        st.dataframe(holdings_df, width="stretch", hide_index=True)
        with st.expander("批量管理 / 清理测试持仓", expanded=False):
            st.caption("先勾选要删除的持仓，再点击确认删除。删除会同时清理该持仓的历史快照。")
            selectable = [
                f"{row['ID']} · {row['代码']} {row['名称']} · {row['状态']} · 剩余{row['剩余数量']}"
                for row in rows
            ]
            selected_delete_labels = st.multiselect("选择要删除的持仓", selectable, key="holding_batch_delete_labels")
            selected_delete_ids = [int(label.split(" · ", 1)[0]) for label in selected_delete_labels]
            confirm_batch_delete = st.checkbox(
                f"确认删除选中的 {len(selected_delete_ids)} 条持仓及其快照",
                value=False,
                key="holding_batch_delete_confirm",
                disabled=not selected_delete_ids,
            )
            c_batch_1, c_batch_2 = st.columns([1, 2])
            if c_batch_1.button("批量删除", type="primary", width="stretch", disabled=not selected_delete_ids or not confirm_batch_delete):
                deleted = service.delete_holdings(selected_delete_ids)
                st.success(f"已删除 {deleted} 条持仓。")
                st.session_state.pop("holding_batch_delete_labels", None)
                st.rerun()
            c_batch_2.info("为了防误删，需要先选择持仓，再勾选确认。")
        numeric_rows = pd.DataFrame(rows).fillna(0)
        chart_tabs = st.tabs(["市值/成本", "浮盈亏", "买入价"])
        with chart_tabs[0]:
            fig = px.bar(numeric_rows, x="名称", y=["成本", "当前市值"], barmode="group", title="持仓成本与当前市值")
            st.plotly_chart(apply_chart_interaction(fig, y_title="金额", x_title="持仓"), width="stretch", key="holding_cost_value")
        with chart_tabs[1]:
            fig = px.bar(numeric_rows, x="名称", y="浮盈亏", color="风险", title="持仓浮盈亏")
            st.plotly_chart(apply_chart_interaction(fig, y_title="浮盈亏", x_title="持仓"), width="stretch", key="holding_profit_loss")
        with chart_tabs[2]:
            fig = px.bar(numeric_rows, x="名称", y="买入价", title="持仓买入价对比")
            st.plotly_chart(apply_chart_interaction(fig, y_title="价格", x_title="持仓"), width="stretch", key="holding_buy_price")
    else:
        st.info("暂无持仓。")

with tabs[2]:
    items = service.list_holdings()
    if items:
        selected_id = st.selectbox("选择持仓", [item.id for item in items], key="holding_detail_select")
        holding = next(item for item in items if item.id == selected_id)
        snap = service.value_holding(holding) if holding.status != "sold" else None
        context = stock_service.get_stock_context(holding.stock_code)
        left, right = st.columns([1, 1])
        with left:
            profit_text = "-" if snap is None else f"{snap.profit_rate:.2%}"
            st.markdown(
                "<div class='decision-card'>"
                f"{badge(holding.stock_code, 'neutral')}"
                f"{badge(holding.status, action_tone('hold' if holding.status != 'sold' else 'avoid'))}"
                f"<div class='mini-note'>{holding.stock_name} | 当前价 {snap.current_price if snap else '-'} | 浮盈亏率 {profit_text}</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            st.json(
                {
                    "holding": {
                        "buy_date": holding.buy_date,
                        "buy_price": holding.buy_price,
                        "quantity": holding.quantity,
                        "current_quantity": holding.current_quantity,
                        "buy_reason": holding.buy_reason,
                        "status": holding.status,
                    },
                    "snapshot": None if not snap else {
                        "current_price": snap.current_price,
                        "market_value": snap.market_value,
                        "profit_amount": snap.profit_amount,
                        "profit_rate": snap.profit_rate,
                        "holding_days": snap.holding_days,
                        "risk_level": snap.risk_level,
                    },
                }
            )
        with right:
            if not context["daily"].empty:
                df = context["daily"].tail(120).copy()
                df["profit_line"] = df["close"] / df["close"].iloc[0] - 1
                fig = px.line(df, x="date", y="profit_line", title="日线累计变化")
                fig.update_traces(hovertemplate="%{x}<br>累计变化 %{y:.2%}<extra></extra>")
                st.plotly_chart(apply_chart_interaction(fig, y_title="累计变化", x_title="日期"), width="stretch", key=f"holding_profit_line_{selected_id}")
            else:
                st.info("暂无图表数据。")
        actions = st.columns(4)
        if actions[0].button("分析持仓", width="stretch"):
            signal = SignalService().analyze_stock(holding.stock_code, holding.stock_name, True, snap.profit_rate if snap else None)
            st.markdown(
                "<div class='decision-card'>"
                f"{badge(signal['action'], action_tone(signal['action']))}"
                f"<div class='mini-note'>{signal['reason']}</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            st.json(signal)
        if actions[1].button("标记已卖出", width="stretch"):
            service.mark_sold(selected_id)
            st.success("已标记卖出。")
            st.rerun()
        if actions[2].button("删除持仓", width="stretch"):
            deleted = service.delete_holding(selected_id)
            st.success("已删除。" if deleted else "该持仓已经不存在。")
            st.rerun()
        if actions[3].button("刷新快照", width="stretch"):
            snap = service.snapshot_holding(holding)
            st.success("快照已刷新。")
    else:
        st.info("暂无持仓。")
