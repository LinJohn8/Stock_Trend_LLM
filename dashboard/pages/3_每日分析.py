from __future__ import annotations

import pandas as pd
import streamlit as st

from database.db import init_db
from services.report_service import ReportService
from services.scheduler_service import SchedulerService
from services.signal_service import SignalService

st.set_page_config(page_title="每日分析", layout="wide")
init_db()

st.title("每日分析")
cols = st.columns(3)
if cols[0].button("手动生成今日分析"):
    signals = SchedulerService().run_daily_job()
    st.success(f"完成 {len(signals)} 条。")
if cols[1].button("生成 HTML 报告"):
    _, path = ReportService().render_daily_html()
    st.success(f"报告已生成：{path}")

signals = SignalService().latest_signals(limit=200)
if signals:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "日期": s.signal_date,
                    "代码": s.stock_code,
                    "名称": s.stock_name,
                    "动作": s.action,
                    "置信度": s.confidence,
                    "综合": s.overall_score,
                    "技术": s.trend_score,
                    "基本面": s.fundamental_score,
                    "估值": s.valuation_score,
                    "资金": s.capital_score,
                    "消息": s.news_score,
                    "风险": s.risk_score,
                    "止损": s.stop_loss_price,
                    "止盈": s.take_profit_price,
                    "理由": s.reason,
                    "风险提示": s.risk_points,
                    "失效条件": s.invalidation_conditions,
                }
                for s in signals
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("暂无分析记录。")
