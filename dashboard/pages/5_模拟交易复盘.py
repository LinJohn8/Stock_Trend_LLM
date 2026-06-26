from __future__ import annotations

import json
from datetime import timedelta
from html import escape

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import select

from dashboard.ui import apply_chart_interaction, inject_global_style, render_static_table
from database.db import init_db, session_scope
from database.models import AISignal, HistoricalSimulation, SignalTracking
from services.backtest_service import BacktestService
from services.historical_simulation_service import HistoricalSimulationService, SimulationConfig
from services.memory_service import MemoryService
from services.simulation_preset_service import SimulationPresetService
from utils.time_utils import now_tz

st.set_page_config(page_title="模拟交易复盘", layout="wide")
init_db()
inject_global_style()

st.title("模拟交易复盘")

tabs = st.tabs(["历史模拟 + 基准对比", "信号追踪复盘"])

with tabs[0]:
    sim_service = HistoricalSimulationService()
    preset_service = SimulationPresetService()
    algorithms = sim_service.algorithm_service.list_algorithms()
    default_algorithm_ids = set(sim_service.algorithm_service.default_algorithm_ids())
    categories = ["全部"] + sorted({algo.category for algo in algorithms})
    presets = preset_service.list_presets()
    preset_options = {"手动选择算法": None}
    preset_options.update({f"{item.name}{' · 默认' if item.is_default else ''}": item.id for item in presets})
    today = now_tz().date()
    with st.form("historical_simulation_form"):
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        stock_code = c1.text_input("股票代码", value="600519")
        stock_name = c2.text_input("股票名称", value="")
        start_date = c3.date_input("开始日期", value=today - timedelta(days=240))
        end_date = c4.date_input("结束日期", value=today)
        preset_label = st.selectbox("算法组", list(preset_options.keys()), help="可以保存一组算法和参数，后续直接复用。")
        selected_preset = next((item for item in presets if item.id == preset_options[preset_label]), None)
        c5, c6, c7 = st.columns([1, 1, 1])
        initial_cash = c5.number_input("初始资金", min_value=100, max_value=10000000, value=100000, step=1000, help="可以很低，例如 100。若低于一手成本，会展示走势和信号，但不会产生买入交易。")
        mode_values = ["consensus", "conservative", "aggressive"]
        benchmark_values = ["sh000300", "sh000001", "sz399001", "sz399006"]
        preset_algo_ids = set(preset_service.algorithm_ids(selected_preset)) if selected_preset else set()
        strategy_mode = c6.selectbox("组合模式", mode_values, index=mode_values.index(selected_preset.strategy_mode) if selected_preset and selected_preset.strategy_mode in mode_values else 0, format_func=lambda x: {"consensus": "共识模式", "conservative": "保守模式", "aggressive": "积极模式"}[x])
        benchmark_code = c7.selectbox("对比基准", benchmark_values, index=benchmark_values.index(selected_preset.benchmark_code) if selected_preset and selected_preset.benchmark_code in benchmark_values else 0, format_func=lambda x: {"sh000300": "沪深300", "sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指"}[x])
        category_filter = st.selectbox("算法分类筛选", categories, help="算法数量较多时，先按分类过滤再多选。")
        visible_algorithms = algorithms if category_filter == "全部" else [algo for algo in algorithms if algo.category == category_filter]
        algo_map = {f"[{algo.category}] {'★ ' if algo.default else ''}{algo.name} - {algo.description}": algo.id for algo in visible_algorithms[:220]}
        default_source = preset_algo_ids or default_algorithm_ids
        default_labels = [label for label, algo_id in algo_map.items() if algo_id in default_source]
        selected_labels = st.multiselect(
            "选择算法",
            list(algo_map.keys()),
            default=default_labels,
            help="默认只选强核心算法。可以单选某个算法，也可以按分类组合多个算法；组合不是简单平均，会经过共识、冲突惩罚、硬风控和记忆惩罚。",
        )
        max_position = st.slider("最大仓位", 0.1, 1.0, float(selected_preset.max_position) if selected_preset else 0.85, 0.05, help="模拟中允许算法最多持有多少仓位，用于控制激进程度。")
        fee_rate = st.number_input("交易费率", min_value=0.0, max_value=0.01, value=float(selected_preset.fee_rate) if selected_preset else 0.0003, step=0.0001, format="%.4f", help="买卖时按成交金额扣除的模拟成本。")
        save_cols = st.columns([1.2, 2, 1])
        preset_name = save_cols[0].text_input("保存为算法组", value="" if not selected_preset else selected_preset.name)
        preset_desc = save_cols[1].text_input("算法组说明", value="" if not selected_preset else selected_preset.description)
        save_preset = save_cols[2].checkbox("运行前保存/更新算法组", value=False)
        submitted = st.form_submit_button("运行历史模拟")

    if submitted:
        if not selected_labels:
            st.error("请至少选择一个算法。")
        else:
            selected_algorithm_ids = [algo_map[label] for label in selected_labels]
            if save_preset:
                try:
                    preset_service.save_preset(
                        name=preset_name,
                        description=preset_desc,
                        selected_algorithms=selected_algorithm_ids,
                        strategy_mode=strategy_mode,
                        benchmark_code=benchmark_code,
                        fee_rate=float(fee_rate),
                        max_position=float(max_position),
                    )
                    st.success(f"已保存算法组：{preset_name}")
                except Exception as exc:
                    st.warning(f"算法组未保存：{exc}")
            with st.spinner("正在回放历史走势并对比基准..."):
                result = sim_service.run(
                    SimulationConfig(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        start_date=start_date,
                        end_date=end_date,
                        initial_cash=float(initial_cash),
                        selected_algorithm_ids=selected_algorithm_ids,
                        strategy_mode=strategy_mode,
                        benchmark_code=benchmark_code,
                        fee_rate=float(fee_rate),
                        max_position=float(max_position),
                    )
                )
            summary = result["summary"]
            lot_cost_hint = None
            curve_df_for_hint = pd.DataFrame(result["equity_curve"])
            if not curve_df_for_hint.empty:
                min_lot_cost = float(curve_df_for_hint["close"].min()) * 100 * (1 + float(fee_rate))
                lot_cost_hint = f"本区间最低一手成本约 {min_lot_cost:.2f}。初始资金 {float(initial_cash):.2f}。"
            cols = st.columns(5)
            cols[0].metric("最终收益", f"{summary['final_return']:.2%}")
            cols[1].metric("基准收益", "-" if summary["benchmark_return"] is None else f"{summary['benchmark_return']:.2%}")
            cols[2].metric("超额收益", "-" if summary["excess_return"] is None else f"{summary['excess_return']:.2%}")
            cols[3].metric("最大回撤", f"{summary['max_drawdown']:.2%}")
            cols[4].metric("交易次数", summary["trade_count"])
            if lot_cost_hint:
                st.markdown(
                    "<div class='status-strip'>"
                    f"<strong>资金/一手约束：</strong>{lot_cost_hint} "
                    "如果资金低于一手成本，系统仍会展示股票走势、算法信号和基准对比，但不会模拟买入成交。"
                    "</div>",
                    unsafe_allow_html=True,
                )

            curve_df = pd.DataFrame(result["equity_curve"])
            if not curve_df.empty:
                curve_df["策略收益"] = curve_df["equity"] / float(initial_cash) - 1
                plot_df = curve_df[["date", "策略收益", "benchmark_return"]].rename(columns={"benchmark_return": "基准收益"})
                fig = px.line(plot_df, x="date", y=["策略收益", "基准收益"], title="策略收益 vs 基准收益", color_discrete_map={"策略收益": "#1a6f55", "基准收益": "#b86f3d"})
                fig.update_traces(hovertemplate="%{x}<br>%{fullData.name} %{y:.2%}<extra></extra>")
                st.plotly_chart(apply_chart_interaction(fig, y_title="收益率", x_title="日期"), width="stretch", key="simulation_latest_curve")
                price_fig = go.Figure()
                price_fig.add_trace(go.Scatter(x=curve_df["date"], y=curve_df["close"], mode="lines", name="股票走势", line=dict(color="#285f86", width=2)))
                trade_df_tmp = pd.DataFrame(result["trades"])
                if not trade_df_tmp.empty:
                    buys = trade_df_tmp[trade_df_tmp["side"] == "buy"]
                    sells = trade_df_tmp[trade_df_tmp["side"] == "sell"]
                    if not buys.empty:
                        price_fig.add_trace(go.Scatter(x=buys["date"], y=buys["price"], mode="markers", name="买入点", marker=dict(color="#1a6f55", size=13, symbol="triangle-up"), customdata=buys[["quantity", "score"]], hovertemplate="买入 %{x}<br>价格 %{y:.2f}<br>数量 %{customdata[0]}<br>评分 %{customdata[1]:.1f}<extra></extra>"))
                    if not sells.empty:
                        price_fig.add_trace(go.Scatter(x=sells["date"], y=sells["price"], mode="markers", name="卖出点", marker=dict(color="#a23d31", size=13, symbol="triangle-down"), customdata=sells[["quantity", "score"]], hovertemplate="卖出 %{x}<br>价格 %{y:.2f}<br>数量 %{customdata[0]}<br>评分 %{customdata[1]:.1f}<extra></extra>"))
                blockers_tmp = pd.DataFrame(result.get("diagnostics", {}).get("trade_blockers", []))
                if not blockers_tmp.empty:
                    blocked_dates = set(blockers_tmp["date"].astype(str))
                    blocked_points = curve_df[curve_df["date"].astype(str).isin(blocked_dates)]
                    if not blocked_points.empty:
                        price_fig.add_trace(go.Scatter(x=blocked_points["date"], y=blocked_points["close"], mode="markers", name="资金不足未成交", marker=dict(color="#a06a16", size=11, symbol="x"), hovertemplate="%{x}<br>资金不足未成交<br>价格 %{y:.2f}<extra></extra>"))
                price_fig.update_layout(title="股票走势与模拟买卖点")
                st.plotly_chart(apply_chart_interaction(price_fig, y_title="价格", x_title="日期"), width="stretch", key="simulation_price_trades")
                projection_df = pd.DataFrame(result.get("price_projection", []))
                if not projection_df.empty:
                    projection_fig = go.Figure()
                    projection_fig.add_trace(go.Scatter(x=projection_df["date"], y=projection_df["actual_close"], mode="lines", name="历史真实走势", line=dict(color="#285f86", width=2)))
                    projection_fig.add_trace(go.Scatter(x=projection_df["date"], y=projection_df["simulated_close"], mode="lines", name="模拟预测走势", line=dict(color="#a06a16", width=2, dash="dash")))
                    projection_fig.update_layout(title="历史真实走势 vs 模拟预测走势")
                    st.plotly_chart(apply_chart_interaction(projection_fig, y_title="价格", x_title="日期"), width="stretch", key="simulation_actual_vs_projection")
                    error = result["summary"].get("projection_error") or {}
                    if error.get("available"):
                        st.info(
                            f"模拟走势误差：平均绝对偏离 {error['mean_abs_gap']:.2%}，"
                            f"最大偏离 {error['max_abs_gap']:.2%}，末日偏离 {error['final_gap']:.2%}。"
                        )
                render_static_table(curve_df.tail(80).to_dict("records"), ["date", "close", "cash", "shares", "equity", "position", "action", "score", "confidence", "benchmark_return"])
            trade_df = pd.DataFrame(result["trades"])
            st.subheader("交易明细")
            render_static_table(trade_df.to_dict("records")) if not trade_df.empty else st.info("本次模拟没有触发交易。若资金低于一手成本，这是正常结果；走势仍可用于观察信号。")
            st.subheader("模拟诊断")
            diagnostics = result.get("diagnostics", {})
            st.info(diagnostics.get("summary", "暂无诊断摘要。"))
            problem_rows = [
                {
                    "算法ID": algo_id,
                    "算法": item.get("name"),
                    "分类": item.get("category"),
                    "状态": item.get("status"),
                    "警告": item.get("warnings", 0),
                    "错误": item.get("errors", 0),
                    "示例": "；".join(str(example.get("message", "")) for example in item.get("examples", [])[:2]),
                }
                for algo_id, item in (diagnostics.get("algorithms") or {}).items()
                if item.get("warnings", 0) or item.get("errors", 0)
            ]
            render_static_table(problem_rows, ["算法ID", "算法", "分类", "状态", "警告", "错误", "示例"]) if problem_rows else st.success("未发现算法执行错误或明显数据缺失。")
            blockers = diagnostics.get("trade_blockers", [])
            render_static_table(blockers, ["date", "code", "message"]) if blockers else st.success("未记录资金/一手限制导致的交易阻塞。")
            st.subheader("AI/本地模拟复盘")
            st.markdown(f"<div class='chat-panel'><div class='chat-answer'>{result.get('ai_review', '暂无复盘')}</div></div>", unsafe_allow_html=True)

    st.subheader("历史模拟记录与对比")
    with st.expander("管理算法组"):
        preset_rows = [
            {
                "ID": item.id,
                "名称": item.name,
                "默认": item.is_default,
                "模式": item.strategy_mode,
                "基准": item.benchmark_code,
                "费率": item.fee_rate,
                "最大仓位": item.max_position,
                "算法数量": len(preset_service.algorithm_ids(item)),
                "说明": item.description,
            }
            for item in preset_service.list_presets()
        ]
        render_static_table(preset_rows, ["ID", "名称", "默认", "模式", "基准", "费率", "最大仓位", "算法数量", "说明"])
        deletable = [item for item in preset_service.list_presets() if not item.is_default]
        if deletable:
            delete_id = st.selectbox("删除非默认算法组", [item.id for item in deletable], format_func=lambda value: next(item.name for item in deletable if item.id == value))
            if st.button("删除所选算法组"):
                preset_service.delete_preset(int(delete_id))
                st.success("已删除算法组。")
                st.rerun()
    runs = sim_service.list_runs(limit=30)
    if runs:
        run_rows = pd.DataFrame(
            [
                {
                    "ID": item.id,
                    "股票": f"{item.stock_code} {item.stock_name}",
                    "区间": f"{item.start_date} ~ {item.end_date}",
                    "模式": item.strategy_mode,
                    "费率": item.fee_rate,
                    "最大仓位": item.max_position,
                    "收益": item.final_return,
                    "基准": item.benchmark_return,
                    "超额": None if item.benchmark_return is None else item.final_return - item.benchmark_return,
                    "回撤": item.max_drawdown,
                    "胜率": item.win_rate,
                    "创建时间": item.created_at,
                }
                for item in runs
            ]
        )
        display_rows = run_rows.copy()
        for col in ["收益", "基准", "超额", "回撤", "胜率"]:
            display_rows[col] = display_rows[col].map(lambda value: "-" if pd.isna(value) else f"{value:.2%}")
        st.dataframe(
            display_rows,
            width="stretch",
            hide_index=True,
        )
        compare_ids = st.multiselect("选择多条模拟记录对比", [item.id for item in runs], default=[runs[0].id])
        selected_runs = [item for item in runs if item.id in set(compare_ids)]
        if selected_runs:
            compare_df = run_rows[run_rows["ID"].isin(compare_ids)].copy()
            fig = px.bar(compare_df, x="ID", y=["收益", "基准", "超额"], barmode="group", title="模拟收益对比")
            fig.update_traces(hovertemplate="ID %{x}<br>%{fullData.name} %{y:.2%}<extra></extra>")
            st.plotly_chart(apply_chart_interaction(fig, y_title="收益率", x_title="模拟 ID"), width="stretch", key="simulation_compare_return")
            fig = px.scatter(compare_df, x="回撤", y="收益", color="模式", size="胜率", hover_data=["股票", "区间"], title="收益 / 回撤 / 胜率对比")
            fig.update_traces(marker=dict(size=12, line=dict(width=1, color="#19231f")), hovertemplate="回撤 %{x:.2%}<br>收益 %{y:.2%}<extra></extra>")
            st.plotly_chart(apply_chart_interaction(fig, y_title="收益率", x_title="最大回撤"), width="stretch", key="simulation_compare_risk_return")
            curves = []
            for item in selected_runs:
                curve = pd.DataFrame(json.loads(item.equity_curve_json))
                if curve.empty:
                    continue
                curve["策略收益"] = curve["equity"] / float(item.initial_cash) - 1
                curve["模拟ID"] = f"#{item.id} {item.strategy_mode}"
                curves.append(curve[["date", "策略收益", "模拟ID"]])
            if curves:
                fig = px.line(pd.concat(curves), x="date", y="策略收益", color="模拟ID", title="保存结果的策略收益曲线对比")
                fig.update_traces(hovertemplate="%{x}<br>%{fullData.name} %{y:.2%}<extra></extra>")
                st.plotly_chart(apply_chart_interaction(fig, y_title="收益率", x_title="日期"), width="stretch", key="simulation_saved_curves")

        st.info("这些结果会保存在数据库里。后续你继续收集新行情后，可以重新跑同一区间或扩大结束日期，再和旧模拟记录对比，观察算法是否需要升级。")
        if st.button("更新行情后重新对比最近一条", width="stretch"):
            latest = runs[0]
            with st.spinner("正在补最新行情并按原参数重跑..."):
                result = sim_service.run(
                    SimulationConfig(
                        stock_code=latest.stock_code,
                        stock_name=latest.stock_name,
                        start_date=latest.start_date,
                        end_date=now_tz().date(),
                        initial_cash=latest.initial_cash,
                        selected_algorithm_ids=json.loads(latest.selected_algorithms),
                        strategy_mode=latest.strategy_mode,
                        benchmark_code=latest.benchmark_code,
                        fee_rate=latest.fee_rate,
                        max_position=latest.max_position,
                    )
                )
            st.success(f"已保存新模拟：收益 {result['summary']['final_return']:.2%}，可在上方多选对比。")

        selected_run_id = st.selectbox("查看模拟记录 ID", [item.id for item in runs])
        selected_run = next(item for item in runs if item.id == selected_run_id)
        saved_projection = pd.DataFrame(json.loads(selected_run.price_projection_json or "[]"))
        if not saved_projection.empty:
            st.subheader("保存的真实走势 vs 模拟预测走势")
            saved_projection_fig = go.Figure()
            saved_projection_fig.add_trace(go.Scatter(x=saved_projection["date"], y=saved_projection["actual_close"], mode="lines", name="历史真实走势", line=dict(color="#285f86", width=2)))
            saved_projection_fig.add_trace(go.Scatter(x=saved_projection["date"], y=saved_projection["simulated_close"], mode="lines", name="模拟预测走势", line=dict(color="#a06a16", width=2, dash="dash")))
            saved_projection_fig.update_layout(title=f"模拟记录 #{selected_run.id} 真实走势 vs 模拟预测走势")
            st.plotly_chart(apply_chart_interaction(saved_projection_fig, y_title="价格", x_title="日期"), width="stretch", key=f"saved_projection_{selected_run.id}")
        saved_diagnostics = json.loads(selected_run.diagnostics_json or "{}")
        if saved_diagnostics:
            st.subheader("保存的诊断与复盘")
            st.info(saved_diagnostics.get("summary", "暂无诊断摘要。"))
            saved_problem_rows = [
                {
                    "算法ID": algo_id,
                    "算法": item.get("name"),
                    "状态": item.get("status"),
                    "警告": item.get("warnings", 0),
                    "错误": item.get("errors", 0),
                    "示例": "；".join(str(example.get("message", "")) for example in item.get("examples", [])[:2]),
                }
                for algo_id, item in (saved_diagnostics.get("algorithms") or {}).items()
                if item.get("warnings", 0) or item.get("errors", 0)
            ]
            if saved_problem_rows:
                render_static_table(saved_problem_rows, ["算法ID", "算法", "状态", "警告", "错误", "示例"])
            blockers = saved_diagnostics.get("trade_blockers", [])
            if blockers:
                render_static_table(blockers, ["date", "code", "message"])
            if selected_run.ai_review:
                st.markdown(f"<div class='chat-panel'><strong>保存的 AI/本地复盘</strong><div class='chat-answer'>{escape(selected_run.ai_review)}</div></div>", unsafe_allow_html=True)
        with st.expander("保存的模拟 JSON"):
            st.json(
                {
                    "summary": json.loads(selected_run.summary_json),
                    "selected_algorithms": json.loads(selected_run.selected_algorithms),
                    "trades": json.loads(selected_run.trades_json),
                    "price_projection": json.loads(selected_run.price_projection_json or "[]")[:10],
                    "diagnostics": saved_diagnostics,
                }
            )
    else:
        st.info("暂无历史模拟记录。")

with tabs[1]:
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
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.info("暂无可复盘建议。")
