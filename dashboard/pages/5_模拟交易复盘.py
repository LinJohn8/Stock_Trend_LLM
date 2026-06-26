from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import select

from dashboard.simulation_view import (
    render_future_forecasts,
    render_latest_simulation_result,
    render_lot_cost_hint,
    render_preset_manager,
    render_run_summary,
    render_saved_runs,
)
from dashboard.ui import inject_global_style, render_anchor, render_page_nav, render_section_shell
from database.db import init_db, session_scope
from database.models import AISignal, HistoricalSimulation, SignalTracking
from services.backtest_service import BacktestService
from services.historical_simulation_service import FutureForecastConfig, HistoricalSimulationService, SimulationConfig
from services.memory_service import MemoryService
from services.simulation_preset_service import SimulationPresetService
from utils.time_utils import now_tz

st.set_page_config(page_title="模拟交易复盘", layout="wide")
init_db()
inject_global_style()

st.title("模拟交易复盘")
render_page_nav(
    [
        ("运行模拟", "simulation-run"),
        ("本次结果", "simulation-result"),
        ("诊断复盘", "simulation-diagnostics"),
        ("未来预测", "simulation-future"),
        ("算法组", "simulation-presets"),
        ("历史记录", "simulation-history"),
    ]
)

tabs = st.tabs(["历史模拟 + 基准对比", "信号追踪复盘"])


def _algorithm_label(algo) -> str:
    return f"[{algo.category}] {'★ ' if algo.default else ''}{algo.name} - {algo.description}"


with tabs[0]:
    render_anchor("simulation-run")
    render_section_shell(
        "历史模拟运行台",
        "选择股票、资金、时间区间、算法组和组合模式后运行；结果会保存，后续可和新数据重新对比。",
        "Simulation Console",
    )
    sim_service = HistoricalSimulationService()
    preset_service = SimulationPresetService()
    algorithms = sim_service.algorithm_service.list_algorithms()
    default_algorithm_ids = set(sim_service.algorithm_service.default_algorithm_ids())
    categories = ["全部"] + sorted({algo.category for algo in algorithms})
    presets = preset_service.list_presets()
    preset_by_id = {item.id: item for item in presets}
    algorithm_label_by_id = {algo.id: _algorithm_label(algo) for algo in algorithms}
    algorithm_id_by_label = {label: algo_id for algo_id, label in algorithm_label_by_id.items()}
    today = now_tz().date()

    preset_options = [None] + [item.id for item in presets]
    preset_id = st.selectbox(
        "算法组",
        preset_options,
        key="simulation_preset_id",
        format_func=lambda value: "手动选择算法" if value is None else f"{preset_by_id[value].name}{' · 默认' if preset_by_id[value].is_default else ''}",
        help="点击算法组后，会自动把该组算法替换到下方“选择算法”里。",
    )
    if st.session_state.get("simulation_last_preset_id") != preset_id:
        st.session_state["simulation_last_preset_id"] = preset_id
        if preset_id is not None:
            selected_preset = preset_by_id[preset_id]
            preset_algo_ids = preset_service.algorithm_ids(selected_preset)
            st.session_state["simulation_selected_algorithm_labels"] = [
                algorithm_label_by_id[algo_id] for algo_id in preset_algo_ids if algo_id in algorithm_label_by_id
            ]
            st.session_state["simulation_strategy_mode"] = selected_preset.strategy_mode
            st.session_state["simulation_benchmark_code"] = selected_preset.benchmark_code
            st.session_state["simulation_fee_rate"] = float(selected_preset.fee_rate)
            st.session_state["simulation_max_position"] = float(selected_preset.max_position)

    if "simulation_selected_algorithm_labels" not in st.session_state:
        st.session_state["simulation_selected_algorithm_labels"] = [
            algorithm_label_by_id[algo_id] for algo_id in default_algorithm_ids if algo_id in algorithm_label_by_id
        ]

    category_filter = st.selectbox("算法分类筛选", categories, key="simulation_category_filter", help="只影响下方列表显示；已选算法即使不在当前分类里也会保留。")
    visible_algorithms = algorithms if category_filter == "全部" else [algo for algo in algorithms if algo.category == category_filter]
    visible_labels = [_algorithm_label(algo) for algo in visible_algorithms[:220]]
    selected_existing = [label for label in st.session_state["simulation_selected_algorithm_labels"] if label in algorithm_id_by_label]
    options = list(dict.fromkeys(visible_labels + selected_existing))
    selected_labels = st.multiselect(
        "选择算法",
        options,
        key="simulation_selected_algorithm_labels",
        help="可以单选某个算法，也可以按分类组合多个算法；组合不是简单平均，会经过共识、冲突惩罚、硬风控和记忆惩罚。",
    )
    selected_algorithm_ids = [algorithm_id_by_label[label] for label in selected_labels if label in algorithm_id_by_label]

    mode_values = ["consensus", "conservative", "aggressive"]
    benchmark_values = ["sh000300", "sh000001", "sz399001", "sz399006"]
    if st.session_state.get("simulation_strategy_mode") not in mode_values:
        st.session_state["simulation_strategy_mode"] = "consensus"
    if st.session_state.get("simulation_benchmark_code") not in benchmark_values:
        st.session_state["simulation_benchmark_code"] = "sh000300"
    st.session_state.setdefault("simulation_fee_rate", 0.0003)
    st.session_state.setdefault("simulation_max_position", 0.85)
    c_mode, c_bench, c_fee, c_pos = st.columns([1, 1, 1, 1])
    strategy_mode = c_mode.selectbox(
        "组合模式",
        mode_values,
        key="simulation_strategy_mode",
        format_func=lambda x: {"consensus": "共识模式", "conservative": "保守模式", "aggressive": "积极模式"}[x],
    )
    benchmark_code = c_bench.selectbox(
        "对比基准",
        benchmark_values,
        key="simulation_benchmark_code",
        format_func=lambda x: {"sh000300": "沪深300", "sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指"}[x],
    )
    fee_rate = c_fee.number_input("交易费率", min_value=0.0, max_value=0.01, step=0.0001, format="%.4f", key="simulation_fee_rate", help="买卖时按成交金额扣除的模拟成本。")
    max_position = c_pos.slider("最大仓位", min_value=0.1, max_value=1.0, step=0.05, key="simulation_max_position", help="模拟中允许算法最多持有多少仓位，用于控制激进程度。")

    @st.dialog("保存当前算法组")
    def save_algorithm_group_dialog() -> None:
        st.caption("会把当前“选择算法”里的算法直接保存为一个可复用算法组。")
        preset_name = st.text_input("算法组名称", value="")
        preset_desc = st.text_area("算法组说明", value="", height=120)
        if st.button("保存算法组", type="primary", width="stretch"):
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
                st.rerun()
            except Exception as exc:
                st.warning(f"算法组未保存：{exc}")

    if st.button("保存当前选择为算法组", width="stretch", disabled=not selected_algorithm_ids):
        save_algorithm_group_dialog()

    with st.form("historical_simulation_form"):
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        stock_code = c1.text_input("股票代码", value="600519")
        stock_name = c2.text_input("股票名称", value="")
        start_date = c3.date_input("开始日期", value=today - timedelta(days=240))
        end_date = c4.date_input("结束日期", value=today)
        c5, c6 = st.columns([1, 1])
        initial_cash = c5.number_input("初始资金", min_value=100, max_value=10000000, value=100000, step=1000, help="可以很低，例如 100。若低于一手成本，会展示走势和信号，但不会产生买入交易。")
        future_horizon = c6.slider("未来预测天数", 5, 120, 20, 5, help="从当前最新行情开始向未来滚动预测，会保存为未来预测记录。")
        submitted = st.form_submit_button("运行历史模拟")
        future_submitted = st.form_submit_button("生成未来趋势预测")

    if submitted:
        if not selected_algorithm_ids:
            st.error("请至少选择一个算法。")
        else:
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
            render_run_summary(result["summary"])
            render_lot_cost_hint(result, float(initial_cash), float(fee_rate))
            render_latest_simulation_result(result, float(initial_cash))

    if future_submitted:
        future_algorithm_ids = selected_algorithm_ids or list(default_algorithm_ids)
        with st.spinner("正在从当前最新行情生成未来趋势预测..."):
            forecast = sim_service.forecast_future(
                FutureForecastConfig(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    horizon_days=int(future_horizon),
                    selected_algorithm_ids=future_algorithm_ids,
                    strategy_mode=strategy_mode,
                    max_position=float(max_position),
                )
            )
        st.success(
            f"已保存未来预测：{forecast['forecast_start_date']} ~ {forecast['forecast_end_date']}，"
            f"最终预测收益 {forecast['summary']['final_forecast_return']:.2%}。"
        )
        if forecast.get("forecast_id"):
            st.session_state["future_forecast_selected_id"] = int(forecast["forecast_id"])
            st.session_state.pop("future_forecast_select", None)

    render_anchor("simulation-future")
    render_future_forecasts(sim_service.list_future_forecasts(stock_code=stock_code, limit=20), sim_service)
    render_preset_manager(preset_service)
    render_saved_runs(sim_service.list_runs(limit=30), sim_service)

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
