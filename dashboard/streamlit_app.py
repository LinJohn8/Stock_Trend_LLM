from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from database.db import init_db
from services.backtest_service import BacktestService
from services.holding_service import HoldingService
from services.portfolio_service import PortfolioService
from services.signal_service import SignalService
from utils.time_utils import is_probable_cn_trading_day, now_tz


st.set_page_config(page_title="股票 AI 辅助决策系统", layout="wide", page_icon="📈")
init_db()


def inject_style() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.4rem; max-width: 1440px; }
        div[data-testid="stMetric"] { background: #f7faf6; border: 1px solid #dfe8df; padding: 14px 16px; border-radius: 6px; }
        .status-strip { padding: 14px 16px; border-left: 5px solid #1e6b57; background: #eef6f2; margin: 8px 0 18px; }
        .risk-strip { padding: 14px 16px; border-left: 5px solid #a33b2f; background: #fff3ed; margin: 8px 0 18px; }
        h1, h2, h3 { letter-spacing: 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_style()
st.title("股票 AI 辅助决策工作台")
st.caption("仅用于个人研究、复盘和辅助决策，不构成投资建议。")

portfolio = PortfolioService()
holding_service = HoldingService()
signals = SignalService().latest_signals(limit=200)
watchlist = portfolio.list_watchlist(active_only=True)
holdings = holding_service.list_holdings(active_only=True)
today = now_tz().date()
today_signals = [s for s in signals if s.signal_date == today]
buy_count = sum(1 for s in today_signals if s.action == "buy_candidate")
reduce_count = sum(1 for s in today_signals if s.action in ["reduce", "sell"])
high_risk_count = sum(1 for s in today_signals if s.risk_score < 35 or s.action in ["avoid", "sell", "reduce"])

st.markdown(
    f"<div class='status-strip'>今天是 {today}，{'预计交易日' if is_probable_cn_trading_day(today) else '可能不是交易日'}。系统偏保守，证据不足会输出 watch 或 uncertain。</div>",
    unsafe_allow_html=True,
)

cols = st.columns(6)
cols[0].metric("自选股", len(watchlist))
cols[1].metric("持仓", len(holdings))
cols[2].metric("买入候选", buy_count)
cols[3].metric("减仓/卖出", reduce_count)
cols[4].metric("高风险", high_risk_count)
market_score = 50 if not today_signals else round(sum(s.overall_score for s in today_signals) / len(today_signals), 1)
cols[5].metric("市场/股票池评分", market_score)

left, right = st.columns([1.5, 1])
with left:
    st.subheader("今日重点关注")
    rows = sorted(today_signals or signals[:20], key=lambda s: (s.risk_score, -s.overall_score))[:5]
    if rows:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "代码": s.stock_code,
                        "名称": s.stock_name,
                        "动作": s.action,
                        "综合": round(s.overall_score, 1),
                        "置信度": round(s.confidence, 0),
                        "建议仓位": s.suggested_position,
                    }
                    for s in rows
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无今日信号。可先添加自选股或持仓，然后手动触发每日分析。")

with right:
    st.subheader("快速操作")
    if st.button("手动触发每日分析", use_container_width=True):
        from services.scheduler_service import SchedulerService

        with st.spinner("正在更新数据并生成分析..."):
            result = SchedulerService().run_daily_job()
        st.success(f"完成，生成 {len(result)} 条信号。")
    if st.button("更新复盘追踪", use_container_width=True):
        updated = BacktestService().update_tracking()
        st.success(f"已更新 {updated} 条追踪记录。")

st.subheader("最新 AI/规则建议")
if signals:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "日期": s.signal_date,
                    "代码": s.stock_code,
                    "名称": s.stock_name,
                    "动作": s.action,
                    "综合": round(s.overall_score, 1),
                    "趋势": round(s.trend_score, 1),
                    "基本面": round(s.fundamental_score, 1),
                    "估值": round(s.valuation_score, 1),
                    "资金": round(s.capital_score, 1),
                    "消息": round(s.news_score, 1),
                    "风险": round(s.risk_score, 1),
                    "理由": s.reason[:120],
                }
                for s in signals[:50]
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("还没有分析记录。")
