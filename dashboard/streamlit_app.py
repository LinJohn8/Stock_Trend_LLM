from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from database.db import init_db
from dashboard.ui import action_tone, badge, inject_global_style, render_hero, render_kpi_grid, render_timeline
from services.backtest_service import BacktestService
from services.dashboard_runtime import start_dashboard_runtime
from services.holding_service import HoldingService
from services.portfolio_service import PortfolioService
from services.signal_service import SignalService
from utils.time_utils import is_probable_cn_trading_day, now_tz


st.set_page_config(page_title="股票 AI 辅助决策系统", layout="wide", page_icon="📈")
init_db()


@st.cache_resource
def _runtime():
    return start_dashboard_runtime()


_runtime()


def inject_style() -> None:
    inject_global_style()


inject_style()

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

market_score = 50 if not today_signals else round(sum(s.overall_score for s in today_signals) / len(today_signals), 1)
render_hero(
    "股票 AI 辅助决策工作台",
    "把行情、新闻证据、算法组合、持仓复盘和学习记忆收束到一个本地工作台。系统只做研究和辅助判断，不进行自动交易。",
    "Local A-share Intelligence",
    [
        (f"{len(watchlist)} 自选", "neutral"),
        (f"{len(holdings)} 持仓", "buy" if holdings else "neutral"),
        (f"{market_score} 池评分", "watch" if market_score < 58 else "buy"),
    ],
)
render_kpi_grid(
    [
        ("自选股", str(len(watchlist)), "当前启用跟踪", "neutral"),
        ("持仓", str(len(holdings)), "真实/模拟仓位", "buy" if holdings else "neutral"),
        ("买入候选", str(buy_count), "今日信号", "buy"),
        ("减仓/卖出", str(reduce_count), "今日风控", "risk" if reduce_count else "neutral"),
        ("高风险", str(high_risk_count), "低风险评分或规避动作", "risk" if high_risk_count else "neutral"),
        ("股票池评分", str(market_score), "今日平均综合分", "watch" if market_score < 58 else "buy"),
    ]
)

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
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("暂无今日信号。可先添加自选股或持仓，然后手动触发每日分析。")

with right:
    st.markdown("<div class='action-panel'><strong>快速操作</strong><div class='mini-note'>这些动作会拉取数据、刷新信号或更新复盘追踪。</div></div>", unsafe_allow_html=True)
    if st.button("手动触发每日分析", width="stretch"):
        from services.scheduler_service import SchedulerService

        render_timeline(
            [
                ("更新行情", "刷新自选股和持仓的最新日线。"),
                ("抓取新闻", "收集并评分相关新闻证据。"),
                ("生成信号", "运行规则、风控和学习记忆修正。"),
                ("发送日报", "按当前邮件配置生成并发送报告。"),
            ]
        )
        with st.spinner("正在运行完整每日分析..."):
            result = SchedulerService().run_daily_job()
        st.success(f"完成，生成 {len(result)} 条信号。")
    if st.button("更新复盘追踪", width="stretch"):
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
        width="stretch",
        hide_index=True,
    )
else:
    st.info("还没有分析记录。")

if signals:
    st.subheader("信号状态速览")
    preview = []
    for signal in signals[:8]:
        preview.append(badge(f"{signal.stock_code} {signal.action}", action_tone(signal.action)))
    st.markdown("".join(preview), unsafe_allow_html=True)
