from __future__ import annotations

import json
from html import escape
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.ui import apply_chart_interaction, render_anchor, render_section_shell, render_static_table
from services.historical_simulation_service import SimulationConfig
from services.simulation_preset_service import SimulationPresetService
from utils.time_utils import now_tz


def render_run_summary(summary: dict[str, Any]) -> None:
    cols = st.columns(5)
    cols[0].metric("最终收益", f"{summary['final_return']:.2%}")
    cols[1].metric("基准收益", "-" if summary["benchmark_return"] is None else f"{summary['benchmark_return']:.2%}")
    cols[2].metric("超额收益", "-" if summary["excess_return"] is None else f"{summary['excess_return']:.2%}")
    cols[3].metric("最大回撤", f"{summary['max_drawdown']:.2%}")
    cols[4].metric("交易次数", summary["trade_count"])


def render_lot_cost_hint(result: dict[str, Any], initial_cash: float, fee_rate: float) -> None:
    curve_df = pd.DataFrame(result["equity_curve"])
    if curve_df.empty:
        return
    min_lot_cost = float(curve_df["close"].min()) * 100 * (1 + float(fee_rate))
    st.markdown(
        "<div class='status-strip'>"
        f"<strong>资金/一手约束：</strong>本区间最低一手成本约 {min_lot_cost:.2f}。初始资金 {float(initial_cash):.2f}。 "
        "如果资金低于一手成本，系统仍会展示股票走势、算法信号和基准对比，但不会模拟买入成交。"
        "</div>",
        unsafe_allow_html=True,
    )


def render_latest_simulation_result(result: dict[str, Any], initial_cash: float) -> None:
    render_anchor("simulation-result")
    render_section_shell(
        "本次模拟结果",
        "收益曲线、买卖点、资金不足标记、真实走势和模拟走势会在这里集中展示。",
        "Latest Result",
    )
    curve_df = pd.DataFrame(result["equity_curve"])
    with st.expander("本次图表：收益、买卖点、真实 vs 模拟走势", expanded=True):
        if curve_df.empty:
            st.info("本次模拟没有可展示的权益曲线。")
        else:
            _render_latest_charts(result, curve_df, initial_cash)
            render_static_table(curve_df.tail(80).to_dict("records"), ["date", "close", "cash", "shares", "equity", "position", "action", "score", "confidence", "benchmark_return"])
    _render_latest_trades(result)
    render_latest_diagnostics(result)


def render_latest_diagnostics(result: dict[str, Any]) -> None:
    render_anchor("simulation-diagnostics")
    render_section_shell(
        "诊断与 AI 复盘",
        "这里会指出算法缺数据、计算异常、资金/一手限制等问题，方便排查为什么某些模拟结果归零或无交易。",
        "Diagnostics",
    )
    with st.expander("模拟诊断 / AI 复盘", expanded=True):
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
        st.markdown(f"<div class='chat-panel'><div class='chat-answer'>{escape(result.get('ai_review', '暂无复盘'))}</div></div>", unsafe_allow_html=True)


def render_preset_manager(preset_service: SimulationPresetService) -> None:
    render_anchor("simulation-presets")
    render_section_shell(
        "算法组管理",
        "把常用算法组合保存成组，后续可复用同一套选择和参数，不需要每次重新勾选。",
        "Preset Library",
    )
    with st.expander("管理算法组"):
        presets = preset_service.list_presets()
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
            for item in presets
        ]
        render_static_table(preset_rows, ["ID", "名称", "默认", "模式", "基准", "费率", "最大仓位", "算法数量", "说明"])
        deletable = [item for item in presets if not item.is_default]
        if deletable:
            delete_id = st.selectbox("删除非默认算法组", [item.id for item in deletable], format_func=lambda value: next(item.name for item in deletable if item.id == value))
            if st.button("删除所选算法组"):
                preset_service.delete_preset(int(delete_id))
                st.success("已删除算法组。")
                st.rerun()


def render_saved_runs(runs: list[Any], sim_service: Any) -> None:
    render_anchor("simulation-history")
    render_section_shell(
        "历史模拟记录与对比",
        "已保存的结果可以多选对比收益、回撤、胜率和保存曲线，也可以用最新行情重跑最近一次配置。",
        "Saved Runs",
    )
    if not runs:
        st.info("暂无历史模拟记录。")
        return
    run_rows = _saved_run_rows(runs)
    display_rows = run_rows.copy()
    for col in ["收益", "基准", "超额", "回撤", "胜率"]:
        display_rows[col] = display_rows[col].map(lambda value: "-" if pd.isna(value) else f"{value:.2%}")
    st.dataframe(display_rows, width="stretch", hide_index=True)
    _render_run_comparisons(runs, run_rows)
    st.info("这些结果会保存在数据库里。后续你继续收集新行情后，可以重新跑同一区间或扩大结束日期，再和旧模拟记录对比，观察算法是否需要升级。")
    _render_rerun_latest(runs, sim_service)
    _render_saved_run_detail(runs)


def render_future_forecasts(forecasts: list[Any], sim_service: Any) -> None:
    render_section_shell(
        "未来趋势预测与后续校验",
        "从当前最新行情开始生成未来模拟趋势并保存；等真实 K 线出现后，系统会在同一条预测记录里显示实际价格对比。",
        "Future Forecast",
    )
    if not forecasts:
        st.info("暂无未来预测记录。运行一次未来趋势预测后会保存在这里。")
        return
    rows = [
        {
            "ID": item.id,
            "股票": f"{item.stock_code} {item.stock_name}",
            "预测区间": f"{item.forecast_start_date} ~ {item.forecast_end_date}",
            "天数": item.horizon_days,
            "起点价": item.base_price,
            "模式": item.strategy_mode,
            "创建时间": item.created_at,
            "已对比天数": len(json.loads(item.comparison_json or "[]")),
        }
        for item in forecasts
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    forecast_ids = [item.id for item in forecasts]
    selected_hint = st.session_state.get("future_forecast_selected_id")
    default_index = forecast_ids.index(selected_hint) if selected_hint in forecast_ids else 0
    selected_id = st.selectbox(
        "查看未来预测记录",
        forecast_ids,
        index=default_index,
        key="future_forecast_select",
        format_func=lambda value: _future_forecast_label(value, forecasts),
    )
    st.session_state["future_forecast_selected_id"] = int(selected_id)
    selected = next(item for item in forecasts if item.id == selected_id)
    if st.button("刷新该预测的真实数据对比", width="stretch", key=f"refresh_future_forecast_{selected.id}"):
        result = sim_service.refresh_future_forecast_comparison(int(selected.id))
        st.success(f"已刷新真实数据对比：当前可对比 {len(result['comparison'])} 个交易日。")
        st.rerun()
    _render_future_forecast_detail(selected)


def _future_forecast_label(value: int, forecasts: list[Any]) -> str:
    item = next((forecast for forecast in forecasts if forecast.id == value), None)
    if not item:
        return str(value)
    return f"#{item.id} · {item.horizon_days}天 · {item.forecast_start_date}~{item.forecast_end_date}"


def _render_latest_charts(result: dict[str, Any], curve_df: pd.DataFrame, initial_cash: float) -> None:
    curve_df["策略收益"] = curve_df["equity"] / float(initial_cash) - 1
    plot_df = curve_df[["date", "策略收益", "benchmark_return"]].rename(columns={"benchmark_return": "基准收益"})
    fig = px.line(plot_df, x="date", y=["策略收益", "基准收益"], title="策略收益 vs 基准收益", color_discrete_map={"策略收益": "#1a6f55", "基准收益": "#b86f3d"})
    fig.update_traces(hovertemplate="%{x}<br>%{fullData.name} %{y:.2%}<extra></extra>")
    st.plotly_chart(apply_chart_interaction(fig, y_title="收益率", x_title="日期"), width="stretch", key="simulation_latest_curve")
    _render_price_trade_chart(result, curve_df)
    _render_projection_chart(result)


def _render_price_trade_chart(result: dict[str, Any], curve_df: pd.DataFrame) -> None:
    price_fig = go.Figure()
    price_fig.add_trace(go.Scatter(x=curve_df["date"], y=curve_df["close"], mode="lines", name="股票走势", line=dict(color="#285f86", width=2)))
    trade_df = pd.DataFrame(result["trades"])
    if not trade_df.empty:
        buys = trade_df[trade_df["side"] == "buy"]
        sells = trade_df[trade_df["side"] == "sell"]
        if not buys.empty:
            price_fig.add_trace(go.Scatter(x=buys["date"], y=buys["price"], mode="markers", name="买入点", marker=dict(color="#1a6f55", size=13, symbol="triangle-up"), customdata=buys[["quantity", "score"]], hovertemplate="买入 %{x}<br>价格 %{y:.2f}<br>数量 %{customdata[0]}<br>评分 %{customdata[1]:.1f}<extra></extra>"))
        if not sells.empty:
            price_fig.add_trace(go.Scatter(x=sells["date"], y=sells["price"], mode="markers", name="卖出点", marker=dict(color="#a23d31", size=13, symbol="triangle-down"), customdata=sells[["quantity", "score"]], hovertemplate="卖出 %{x}<br>价格 %{y:.2f}<br>数量 %{customdata[0]}<br>评分 %{customdata[1]:.1f}<extra></extra>"))
    blockers = pd.DataFrame(result.get("diagnostics", {}).get("trade_blockers", []))
    if not blockers.empty:
        blocked_dates = set(blockers["date"].astype(str))
        blocked_points = curve_df[curve_df["date"].astype(str).isin(blocked_dates)]
        if not blocked_points.empty:
            price_fig.add_trace(go.Scatter(x=blocked_points["date"], y=blocked_points["close"], mode="markers", name="资金不足未成交", marker=dict(color="#a06a16", size=11, symbol="x"), hovertemplate="%{x}<br>资金不足未成交<br>价格 %{y:.2f}<extra></extra>"))
    price_fig.update_layout(title="股票走势与模拟买卖点")
    st.plotly_chart(apply_chart_interaction(price_fig, y_title="价格", x_title="日期"), width="stretch", key="simulation_price_trades")


def _render_projection_chart(result: dict[str, Any]) -> None:
    projection_df = pd.DataFrame(result.get("price_projection", []))
    if projection_df.empty:
        return
    view_mode = st.radio(
        "走势对比视图",
        ["整体趋势", "只看局部上升"],
        horizontal=True,
        key="simulation_projection_view_mode",
        help="局部上升视图保留日期轴，把模拟走势的非上涨波动压平，只显示哪些时间段贡献了局部上涨。",
    )
    if view_mode == "只看局部上升":
        _render_local_rise_projection(projection_df, result)
    else:
        _render_overall_projection(projection_df, result)
    error = result["summary"].get("projection_error") or {}
    if error.get("available"):
        st.info(f"模拟走势误差：平均绝对偏离 {error['mean_abs_gap']:.2%}，最大偏离 {error['max_abs_gap']:.2%}，末日偏离 {error['final_gap']:.2%}。")


def _render_overall_projection(projection_df: pd.DataFrame, result: dict[str, Any], *, key_suffix: str = "latest") -> None:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=projection_df["date"], y=projection_df["actual_close"], mode="lines", name="历史真实走势", line=dict(color="#285f86", width=2)))
    fig.add_trace(go.Scatter(x=projection_df["date"], y=projection_df["simulated_close"], mode="lines", name="模拟预测走势", line=dict(color="#a06a16", width=2, dash="dash")))
    _add_trade_markers(fig, result.get("trades", []))
    fig.update_layout(title="历史真实走势 vs 模拟预测走势")
    st.plotly_chart(apply_chart_interaction(fig, y_title="价格", x_title="日期"), width="stretch", key=f"simulation_actual_vs_projection_{key_suffix}")


def _render_local_rise_projection(projection_df: pd.DataFrame, result: dict[str, Any], *, key_suffix: str = "latest") -> None:
    flattened = _flatten_local_rise_projection(projection_df)
    if flattened.empty:
        st.info("没有可展示的局部上升数据，已显示整体趋势图。")
        _render_overall_projection(projection_df, result, key_suffix=f"{key_suffix}_fallback")
        return
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=flattened["date"],
            y=flattened["actual_close"],
            mode="lines",
            name="原始真实走势",
            line=dict(color="#285f86", width=2),
            customdata=flattened[["actual_return"]],
            hovertemplate="日期 %{x}<br>真实价 %{y:.2f}<br>真实收益 %{customdata[0]:.2%}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=flattened["date"],
            y=flattened["simulated_flat_rise"],
            mode="lines",
            name="模拟局部上升压平线",
            line=dict(color="#a06a16", width=2, dash="dash"),
            customdata=flattened[["simulated_close", "simulated_delta", "rise_only_gain", "is_rise"]],
            hovertemplate=(
                "日期 %{x}<br>"
                "压平模拟价 %{y:.2f}<br>"
                "原始模拟价 %{customdata[0]:.2f}<br>"
                "当日模拟变化 %{customdata[1]:.2f}<br>"
                "累计上涨贡献 %{customdata[2]:.2f}<br>"
                "是否上涨 %{customdata[3]}<extra></extra>"
            ),
        )
    )
    rise_points = flattened[flattened["is_rise"] == "是"]
    if not rise_points.empty:
        fig.add_trace(
            go.Scatter(
                x=rise_points["date"],
                y=rise_points["simulated_flat_rise"],
                mode="markers",
                name="局部上升发生点",
                marker=dict(color="#1a6f55", size=8, symbol="circle"),
                customdata=rise_points[["simulated_close", "simulated_delta", "rise_only_gain"]],
                hovertemplate="局部上升 %{x}<br>压平价 %{y:.2f}<br>原始模拟价 %{customdata[0]:.2f}<br>上涨贡献 %{customdata[1]:.2f}<br>累计贡献 %{customdata[2]:.2f}<extra></extra>",
            )
        )
    _add_flat_trade_markers(fig, flattened, result.get("trades", []))
    fig.update_layout(title="原始真实走势 vs 模拟局部上升压平线")
    st.plotly_chart(apply_chart_interaction(fig, y_title="价格 / 压平价格", x_title="日期"), width="stretch", key=f"simulation_local_rise_projection_{key_suffix}")
    st.caption("局部上升压平线保留原始日期轴：模拟走势下跌或横盘时保持不动，只在模拟价格上涨的日期累积上升，用来定位“哪里局部上升对上了”。")


def _flatten_local_rise_projection(projection_df: pd.DataFrame) -> pd.DataFrame:
    if projection_df.empty:
        return pd.DataFrame()
    rows = []
    base_price = float(projection_df.iloc[0]["simulated_close"])
    flat_price = base_price
    previous_simulated: float | None = None
    for item in projection_df.to_dict("records"):
        simulated = float(item["simulated_close"])
        actual = float(item["actual_close"])
        delta = 0.0 if previous_simulated is None else simulated - previous_simulated
        positive_delta = max(0.0, delta)
        flat_price += positive_delta
        rows.append(
            {
                **item,
                "actual_close": actual,
                "simulated_close": simulated,
                "simulated_delta": delta,
                "rise_only_gain": flat_price - base_price,
                "simulated_flat_rise": flat_price,
                "is_rise": "是" if positive_delta > 0 else "否",
            }
        )
        previous_simulated = simulated
    return pd.DataFrame(rows)


def _add_trade_markers(fig: go.Figure, trades: list[dict[str, Any]]) -> None:
    trade_df = pd.DataFrame(trades)
    if trade_df.empty:
        return
    for side, name, color, symbol in [
        ("buy", "模拟买入", "#1a6f55", "triangle-up"),
        ("sell", "模拟卖出", "#a23d31", "triangle-down"),
    ]:
        subset = trade_df[trade_df["side"] == side]
        if subset.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=subset["date"],
                y=subset["price"],
                mode="markers",
                name=name,
                marker=dict(color=color, size=14, symbol=symbol, line=dict(width=1, color="#19231f")),
                customdata=subset[["quantity", "fee", "score", "reason"]],
                hovertemplate=f"{name} %{{x}}<br>价格 %{{y:.2f}}<br>数量 %{{customdata[0]}}<br>费用 %{{customdata[1]:.2f}}<br>评分 %{{customdata[2]:.1f}}<br>理由 %{{customdata[3]}}<extra></extra>",
            )
        )


def _add_flat_trade_markers(fig: go.Figure, flattened: pd.DataFrame, trades: list[dict[str, Any]]) -> None:
    if flattened.empty or not trades:
        return
    trade_df = pd.DataFrame(trades)
    for side, name, color, symbol in [
        ("buy", "压平线买入点", "#1a6f55", "triangle-up"),
        ("sell", "压平线卖出点", "#a23d31", "triangle-down"),
    ]:
        markers = []
        for trade in trade_df[trade_df["side"] == side].to_dict("records"):
            matches = flattened[flattened["date"].astype(str) == str(trade["date"])]
            for _, match in matches.iterrows():
                markers.append(
                    {
                        **trade,
                        "flat_price": match["simulated_flat_rise"],
                        "simulated_close": match["simulated_close"],
                        "is_rise": match["is_rise"],
                    }
                )
        if not markers:
            continue
        marker_df = pd.DataFrame(markers)
        fig.add_trace(
            go.Scatter(
                x=marker_df["date"],
                y=marker_df["flat_price"],
                mode="markers",
                name=name,
                marker=dict(color=color, size=13, symbol=symbol, line=dict(width=1, color="#19231f")),
                customdata=marker_df[["price", "simulated_close", "quantity", "score", "is_rise", "reason"]],
                hovertemplate=f"{name} %{{x}}<br>压平线价 %{{y:.2f}}<br>交易价 %{{customdata[0]:.2f}}<br>原始模拟价 %{{customdata[1]:.2f}}<br>数量 %{{customdata[2]}}<br>评分 %{{customdata[3]:.1f}}<br>当日是否上涨 %{{customdata[4]}}<br>理由 %{{customdata[5]}}<extra></extra>",
            )
        )


def _render_latest_trades(result: dict[str, Any]) -> None:
    trade_df = pd.DataFrame(result["trades"])
    with st.expander("交易明细", expanded=not trade_df.empty):
        render_static_table(trade_df.to_dict("records")) if not trade_df.empty else st.info("本次模拟没有触发交易。若资金低于一手成本，这是正常结果；走势仍可用于观察信号。")


def _saved_run_rows(runs: list[Any]) -> pd.DataFrame:
    return pd.DataFrame(
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


def _render_run_comparisons(runs: list[Any], run_rows: pd.DataFrame) -> None:
    compare_ids = st.multiselect("选择多条模拟记录对比", [item.id for item in runs], default=[runs[0].id])
    selected_runs = [item for item in runs if item.id in set(compare_ids)]
    if not selected_runs:
        return
    compare_df = run_rows[run_rows["ID"].isin(compare_ids)].copy()
    fig = px.bar(compare_df, x="ID", y=["收益", "基准", "超额"], barmode="group", title="模拟收益对比")
    fig.update_traces(hovertemplate="ID %{x}<br>%{fullData.name} %{y:.2%}<extra></extra>")
    st.plotly_chart(apply_chart_interaction(fig, y_title="收益率", x_title="模拟 ID"), width="stretch", key="simulation_compare_return")
    fig = px.scatter(compare_df, x="回撤", y="收益", color="模式", size="胜率", hover_data=["股票", "区间"], title="收益 / 回撤 / 胜率对比")
    fig.update_traces(marker=dict(size=12, line=dict(width=1, color="#19231f")), hovertemplate="回撤 %{x:.2%}<br>收益 %{y:.2%}<extra></extra>")
    st.plotly_chart(apply_chart_interaction(fig, y_title="收益率", x_title="最大回撤"), width="stretch", key="simulation_compare_risk_return")
    _render_saved_curves(selected_runs)


def _render_saved_curves(selected_runs: list[Any]) -> None:
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


def _render_rerun_latest(runs: list[Any], sim_service: Any) -> None:
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


def _render_saved_run_detail(runs: list[Any]) -> None:
    selected_run_id = st.selectbox("查看模拟记录 ID", [item.id for item in runs])
    selected_run = next(item for item in runs if item.id == selected_run_id)
    _render_saved_projection(selected_run)
    saved_diagnostics = json.loads(selected_run.diagnostics_json or "{}")
    _render_saved_diagnostics(selected_run, saved_diagnostics)
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


def _render_saved_projection(selected_run: Any) -> None:
    saved_projection = pd.DataFrame(json.loads(selected_run.price_projection_json or "[]"))
    if saved_projection.empty:
        return
    st.subheader("保存的真实走势 vs 模拟预测走势")
    view_mode = st.radio(
        "保存记录走势视图",
        ["整体趋势", "只看局部上升"],
        horizontal=True,
        key=f"saved_projection_view_mode_{selected_run.id}",
        help="局部上升视图会忽略整体偏移，专门看上涨片段的节奏是否贴合。",
    )
    result = {
        "trades": json.loads(selected_run.trades_json or "[]"),
        "summary": json.loads(selected_run.summary_json or "{}"),
    }
    if view_mode == "只看局部上升":
        _render_local_rise_projection(saved_projection, result, key_suffix=f"saved_{selected_run.id}")
    else:
        _render_overall_projection(saved_projection, result, key_suffix=f"saved_{selected_run.id}")


def _render_saved_diagnostics(selected_run: Any, saved_diagnostics: dict[str, Any]) -> None:
    if not saved_diagnostics:
        return
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


def _render_future_forecast_detail(selected: Any) -> None:
    projection = pd.DataFrame(json.loads(selected.projection_json or "[]"))
    comparison = pd.DataFrame(json.loads(selected.comparison_json or "[]"))
    summary = json.loads(selected.summary_json or "{}")
    if projection.empty:
        st.info("这条未来预测没有可展示的曲线。")
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=projection["date"], y=projection["forecast_price"], mode="lines", name="未来预测价", line=dict(color="#a06a16", width=2, dash="dash")))
    if not comparison.empty:
        fig.add_trace(go.Scatter(x=comparison["date"], y=comparison["actual_close"], mode="lines", name="已出现真实收盘价", line=dict(color="#285f86", width=2)))
        fig.add_trace(
            go.Scatter(
                x=comparison["date"],
                y=comparison["forecast_price"],
                mode="markers",
                name="预测对比点",
                marker=dict(color="#1a6f55", size=10, symbol="circle"),
                customdata=comparison[["actual_close", "gap_pct", "score", "action"]],
                hovertemplate="日期 %{x}<br>预测 %{y:.2f}<br>真实 %{customdata[0]:.2f}<br>偏差 %{customdata[1]:.2%}<br>评分 %{customdata[2]:.1f}<br>动作 %{customdata[3]}<extra></extra>",
            )
        )
    fig.update_layout(title=f"未来预测 #{selected.id}：预测走势 vs 后续真实走势")
    st.plotly_chart(apply_chart_interaction(fig, y_title="价格", x_title="日期"), width="stretch", key=f"future_forecast_{selected.id}")
    st.info(
        "预测摘要："
        f"最终预测收益 {summary.get('final_forecast_return', 0):.2%}，"
        f"最高预测收益 {summary.get('max_forecast_return', 0):.2%}，"
        f"已对比 {summary.get('comparison_points', 0)} 个真实交易日。"
    )
    render_static_table(projection.tail(80).to_dict("records"), ["date", "step", "forecast_price", "forecast_return", "score", "confidence", "action", "target_fraction"])
    if not comparison.empty:
        render_static_table(comparison.tail(80).to_dict("records"), ["date", "forecast_price", "actual_close", "gap_pct", "forecast_return", "actual_return", "action", "score"])
