from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd
from sqlalchemy import select

from database.db import session_scope
from database.models import AlgorithmRun, Holding, LearningMemory
from services.fundamental_service import FundamentalService
from services.indicator_service import IndicatorService
from services.news_ingestion_service import NewsIngestionService
from services.risk_service import RiskService
from services.sentiment_service import SentimentService
from services.stock_data_service import StockDataService
from utils.math_utils import clamp
from utils.stock_utils import normalize_stock_code
from utils.time_utils import now_tz


@dataclass(frozen=True)
class AnalysisAlgorithm:
    id: str
    name: str
    description: str
    weight: float
    runner: Callable[[dict[str, Any]], dict[str, Any]]
    category: str = "core"
    default: bool = False
    tier: str = "standard"


@dataclass(frozen=True)
class AlgorithmTemplate:
    id: str
    name: str
    category: str
    description: str
    weight: float
    params: dict[str, Any]
    tier: str = "standard"


class AlgorithmService:
    """Selectable deterministic analysis algorithms for dashboard use."""

    DEFAULT_ALGORITHM_IDS = [
        "trend_following",
        "momentum",
        "valuation",
        "capital_volume",
        "news_risk",
        "risk_guard_drawdown_15",
        "trend_ma20_breakout_3",
        "momentum_ret20_8",
        "volume_price_confirm_20_1_5",
        "learning_memory",
    ]

    def list_algorithms(self) -> list[AnalysisAlgorithm]:
        core = [
            AnalysisAlgorithm("trend_following", "核心·趋势跟踪", "均线结构、价格位置和趋势延续性。", 0.22, self._trend_following, "核心", True, "core"),
            AnalysisAlgorithm("momentum", "核心·动量强弱", "近 5/20/60 日收益、RSI、MACD。", 0.16, self._momentum, "核心", True, "core"),
            AnalysisAlgorithm("mean_reversion", "核心·回撤修复", "超跌、偏离均线、波动收敛后的修复可能性。", 0.10, self._mean_reversion, "核心", False, "core"),
            AnalysisAlgorithm("valuation", "核心·估值检查", "PE/PB 与第一版估值安全边际。", 0.14, self._valuation, "核心", True, "core"),
            AnalysisAlgorithm("capital_volume", "核心·资金量价", "成交量、量比、放量方向和换手风险。", 0.14, self._capital_volume, "核心", True, "core"),
            AnalysisAlgorithm("news_risk", "核心·新闻风险", "公告/新闻关键词、负面事件和不确定性。", 0.12, self._news_risk, "核心", True, "core"),
            AnalysisAlgorithm("holding_review", "核心·持仓复核", "持仓盈亏、止损止盈、买入逻辑是否仍成立。", 0.08, self._holding_review, "核心", False, "core"),
            AnalysisAlgorithm("learning_memory", "核心·历史记忆", "历史错误复盘中反复出现的问题。", 0.04, self._learning_memory, "核心", True, "core"),
        ]
        generated = [
            AnalysisAlgorithm(
                template.id,
                template.name,
                template.description,
                template.weight,
                lambda ctx, tpl=template: self._run_template(ctx, tpl),
                template.category,
                template.id in self.DEFAULT_ALGORITHM_IDS,
                template.tier,
            )
            for template in self._generated_templates()
        ]
        return core + generated

    def default_algorithm_ids(self) -> list[str]:
        available = {algo.id for algo in self.list_algorithms()}
        return [algo_id for algo_id in self.DEFAULT_ALGORITHM_IDS if algo_id in available]

    def algorithm_categories(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for algo in self.list_algorithms():
            counts[algo.category] = counts.get(algo.category, 0) + 1
        return counts

    def run(
        self,
        stock_code: str,
        stock_name: str = "",
        selected_algorithm_ids: list[str] | None = None,
        fetch_data: bool = True,
    ) -> dict[str, Any]:
        code = normalize_stock_code(stock_code)
        if fetch_data:
            StockDataService().update_daily_data(code)
        context = self._build_context(code, stock_name)
        algorithms = self.list_algorithms()
        if selected_algorithm_ids:
            selected = [algo for algo in algorithms if algo.id in set(selected_algorithm_ids)]
        else:
            default_ids = set(self.default_algorithm_ids())
            selected = [algo for algo in algorithms if algo.id in default_ids]
        if not selected:
            selected = [algo for algo in algorithms if algo.default] or algorithms[:8]
        results = [self._normalize_result(algo.runner(context), algo) for algo in selected]
        decision = self.combine_results(results, context)
        overall_score = decision["overall_score"]
        action = decision["action"]
        confidence = decision["confidence"]
        output = {
            "stock_code": code,
            "stock_name": stock_name,
            "run_date": now_tz().date(),
            "selected_algorithms": [algo.id for algo in selected],
            "overall_score": overall_score,
            "action": action,
            "confidence": confidence,
            "results": results,
            "combination": decision,
            "summary": self._summary(action, overall_score, results, decision),
            "disclaimer": "仅用于个人研究和辅助决策，不构成投资建议。",
        }
        self.save_run(output)
        return output

    def save_run(self, output: dict[str, Any]) -> AlgorithmRun:
        with session_scope() as session:
            item = AlgorithmRun(
                stock_code=output["stock_code"],
                stock_name=output.get("stock_name", ""),
                run_date=output["run_date"],
                selected_algorithms=json.dumps(output["selected_algorithms"], ensure_ascii=False),
                result_json=json.dumps(output, ensure_ascii=False, default=str),
                overall_score=output["overall_score"],
                action=output["action"],
                confidence=output["confidence"],
            )
            session.add(item)
            session.flush()
            session.refresh(item)
            return item

    def list_runs(self, stock_code: str | None = None, limit: int = 100) -> list[AlgorithmRun]:
        with session_scope() as session:
            stmt = select(AlgorithmRun).order_by(AlgorithmRun.created_at.desc()).limit(limit)
            if stock_code:
                stmt = stmt.where(AlgorithmRun.stock_code == normalize_stock_code(stock_code))
            return list(session.scalars(stmt).all())

    def _build_context(self, stock_code: str, stock_name: str) -> dict[str, Any]:
        technical = IndicatorService().calculate(stock_code)
        fundamental = FundamentalService().analyze(stock_code)
        sentiment = SentimentService().analyze(stock_code)
        risk = RiskService().evaluate(stock_name, technical, sentiment, self._holding_profit_rate(stock_code))
        df = StockDataService().get_daily_dataframe(stock_code, limit=120)
        return {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "technical": technical,
            "fundamental": fundamental,
            "sentiment": sentiment,
            "news_evidence": NewsIngestionService().get_evidence(stock_code, limit=8),
            "risk": risk,
            "daily": df,
            "holding": self._holding(stock_code),
            "memories": self._memories(stock_code),
        }

    def _trend_following(self, ctx: dict[str, Any]) -> dict[str, Any]:
        t = ctx["technical"]
        score = t.get("trend_score", 50)
        reasons = [t.get("technical_summary", "技术面数据不足。")]
        direction = "neutral"
        if t.get("current_price") and t.get("ma20") and t["current_price"] < t["ma20"]:
            reasons.append("价格低于 MA20，趋势跟踪算法降低评分。")
            direction = "bearish"
        elif score >= 65:
            direction = "bullish"
        return {"score": clamp(score), "view": "trend", "direction": direction, "position_bias": _position_bias(score), "reasons": reasons, "risks": []}

    def _momentum(self, ctx: dict[str, Any]) -> dict[str, Any]:
        t = ctx["technical"]
        score = t.get("momentum_score", 50)
        risks = []
        if t.get("rsi") and t["rsi"] > 75:
            risks.append("RSI 偏高，短线过热。")
        if t.get("ret20", 0) > 0.30:
            risks.append("近 20 日涨幅过大，追高风险增加。")
        direction = "bullish" if 58 <= score <= 78 and not risks else "bearish" if score < 42 else "neutral"
        return {"score": clamp(score), "view": "momentum", "direction": direction, "position_bias": _position_bias(score), "reasons": [f"近20日收益 {t.get('ret20', 0):.2%}，RSI {t.get('rsi') or '-'}。"], "risks": risks}

    def _mean_reversion(self, ctx: dict[str, Any]) -> dict[str, Any]:
        t = ctx["technical"]
        score = 50
        reasons = []
        if t.get("rsi") and t["rsi"] < 35:
            score += 15
            reasons.append("RSI 较低，存在超跌修复观察价值。")
        if t.get("max_drawdown", 0) < -0.15:
            score += 8
            reasons.append("近期回撤较大，但需要确认风险释放是否结束。")
        if t.get("current_price") and t.get("ma60") and t["current_price"] < t["ma60"]:
            score -= 12
            reasons.append("价格仍低于 MA60，修复交易需要更谨慎。")
        direction = "bullish" if score >= 60 else "bearish" if score < 42 else "neutral"
        return {"score": clamp(score), "view": "mean_reversion", "direction": direction, "position_bias": min(0.18, _position_bias(score)), "reasons": reasons or ["未出现明显均值回归信号。"], "risks": ["超跌不等于反转，需要等待确认。"]}

    def _valuation(self, ctx: dict[str, Any]) -> dict[str, Any]:
        f = ctx["fundamental"]
        score = f.get("valuation_score", 50)
        risks = []
        if f.get("pe") and f["pe"] > 80:
            risks.append("PE 偏高，估值安全边际不足。")
        direction = "bullish" if score >= 62 else "bearish" if score < 42 or risks else "neutral"
        return {"score": clamp(score), "view": "valuation", "direction": direction, "position_bias": _position_bias(score), "reasons": [f.get("fundamental_summary", "估值数据不足。")], "risks": risks}

    def _capital_volume(self, ctx: dict[str, Any]) -> dict[str, Any]:
        t = ctx["technical"]
        score = 50
        reasons = []
        risks = []
        vr = t.get("volume_ratio")
        if vr and 0.8 <= vr <= 1.8:
            score += 12
            reasons.append("量比相对温和，未见异常放量。")
        if vr and vr > 2 and t.get("ret5", 0) < 0:
            score -= 18
            risks.append("放量下跌，资金面需谨慎。")
        direction = "bearish" if risks else "bullish" if score >= 60 else "neutral"
        return {"score": clamp(score), "view": "capital_volume", "direction": direction, "position_bias": _position_bias(score), "reasons": reasons or [f"量比 {vr or '-'}。"], "risks": risks}

    def _news_risk(self, ctx: dict[str, Any]) -> dict[str, Any]:
        s = ctx["sentiment"]
        evidence = ctx.get("news_evidence", [])
        score = s.get("news_score", 50)
        risks = []
        if s.get("news_risk_level") != "low":
            risks.append(s.get("news_summary", "消息面不确定。"))
        if evidence and max(item.get("reliability_score", 0) for item in evidence) < 45:
            risks.append("新闻证据可靠度偏低，需要等待更多来源交叉验证。")
        direction = "bearish" if risks or score < 42 else "bullish" if score >= 62 else "neutral"
        return {"score": clamp(score), "view": "news_risk", "direction": direction, "position_bias": min(0.2, _position_bias(score)), "reasons": [s.get("news_summary", "暂无消息面数据。")], "risks": risks}

    def _holding_review(self, ctx: dict[str, Any]) -> dict[str, Any]:
        holding = ctx.get("holding")
        if not holding:
            return {"score": 50, "view": "holding_review", "direction": "neutral", "position_bias": 0, "reasons": ["未记录持仓，此算法仅作中性处理。"], "risks": []}
        profit = holding.get("profit_rate")
        score = 55
        risks = []
        if profit is not None and profit <= -0.08:
            score -= 25
            risks.append("持仓亏损超过 -8%，触发止损复核。")
        if profit is not None and profit >= 0.20:
            risks.append("持仓盈利超过 20%，建议考虑移动止盈。")
        direction = "bearish" if profit is not None and profit <= -0.08 else "neutral"
        return {"score": clamp(score), "view": "holding_review", "direction": direction, "position_bias": _position_bias(score), "reasons": [f"当前持仓收益 {profit:.2%}" if profit is not None else "持仓收益暂不可得。"], "risks": risks}

    def _learning_memory(self, ctx: dict[str, Any]) -> dict[str, Any]:
        memories = ctx.get("memories", [])
        if not memories:
            return {"score": 50, "view": "learning_memory", "direction": "neutral", "position_bias": 0, "reasons": ["暂无该股票历史学习记忆。"], "risks": []}
        open_failures = [m for m in memories if m.get("outcome") == "failed" and m.get("status") != "ignored"]
        score = 50 - min(20, len(open_failures) * 5)
        return {
            "score": clamp(score),
            "view": "learning_memory",
            "direction": "bearish" if open_failures else "neutral",
            "position_bias": 0,
            "reasons": [f"找到 {len(memories)} 条历史记忆，其中未忽略失败样本 {len(open_failures)} 条。"],
            "risks": [m.get("lesson", "") for m in open_failures[:3]],
        }

    def _generated_templates(self) -> list[AlgorithmTemplate]:
        templates: list[AlgorithmTemplate] = []
        for window in [5, 10, 20, 30, 60, 90, 120, 250]:
            for buffer in [0, 1, 2, 3]:
                templates.append(
                    AlgorithmTemplate(
                        id=f"trend_ma{window}_breakout_{buffer}",
                        name=f"趋势·MA{window}突破·缓冲{buffer}%",
                        category="趋势",
                        description=f"价格相对 MA{window} 的突破/跌破判断，带 {buffer}% 缓冲。",
                        weight=0.045,
                        params={"kind": "trend_ma", "window": window, "buffer": buffer / 100},
                        tier="strong" if window in {20, 60} and buffer in {1, 3} else "standard",
                    )
                )
        for fast, slow in [(5, 20), (5, 60), (10, 20), (10, 60), (20, 60), (30, 90)]:
            for margin in [0, 1, 2]:
                templates.append(
                    AlgorithmTemplate(
                        id=f"trend_cross_{fast}_{slow}_{margin}",
                        name=f"趋势·MA{fast}/MA{slow}结构·{margin}%",
                        category="趋势",
                        description=f"MA{fast} 与 MA{slow} 的多空排列和结构强弱。",
                        weight=0.042,
                        params={"kind": "ma_cross", "fast": fast, "slow": slow, "margin": margin / 100},
                    )
                )
        for period in [5, 10, 20, 30, 60, 90, 120]:
            for threshold in [3, 5, 8, 12, 18, 25]:
                templates.append(
                    AlgorithmTemplate(
                        id=f"momentum_ret{period}_{threshold}",
                        name=f"动量·{period}日收益>{threshold}%",
                        category="动量",
                        description=f"近 {period} 日收益强弱与追高风险判断。",
                        weight=0.038,
                        params={"kind": "return_momentum", "period": period, "threshold": threshold / 100},
                        tier="strong" if period in {20, 60} and threshold in {5, 8} else "standard",
                    )
                )
        for low, high in [(25, 70), (30, 70), (35, 75), (40, 80), (30, 80)]:
            templates.append(
                AlgorithmTemplate(
                    id=f"momentum_rsi_{low}_{high}",
                    name=f"动量·RSI区间{low}-{high}",
                    category="动量",
                    description="RSI 过热/过冷与动量延续质量。",
                    weight=0.035,
                    params={"kind": "rsi_band", "low": low, "high": high},
                )
            )
        for period in [10, 20, 30, 60, 90, 120]:
            for drawdown in [8, 12, 15, 20, 25, 30]:
                templates.append(
                    AlgorithmTemplate(
                        id=f"mean_reversion_dd{period}_{drawdown}",
                        name=f"均值回归·{period}日回撤{drawdown}%",
                        category="均值回归",
                        description=f"近 {period} 日回撤后的修复可能与趋势过滤。",
                        weight=0.032,
                        params={"kind": "drawdown_reversion", "period": period, "drawdown": -drawdown / 100},
                    )
                )
        for ma in [5, 10, 20, 60, 120]:
            for distance in [3, 5, 8, 12]:
                templates.append(
                    AlgorithmTemplate(
                        id=f"mean_reversion_ma{ma}_dist{distance}",
                        name=f"均值回归·偏离MA{ma} {distance}%",
                        category="均值回归",
                        description=f"价格偏离 MA{ma} 后的回归/破位判断。",
                        weight=0.03,
                        params={"kind": "ma_distance", "ma": ma, "distance": distance / 100},
                    )
                )
        for threshold in [20, 30, 40, 50, 65, 80]:
            templates.append(
                AlgorithmTemplate(
                    id=f"volatility_guard_{threshold}",
                    name=f"波动·年化波动阈值{threshold}%",
                    category="波动",
                    description="年化波动过高时降低进攻分，低波动趋势时加分。",
                    weight=0.028,
                    params={"kind": "volatility_guard", "threshold": threshold / 100},
                )
            )
        for period in [10, 20, 30, 60]:
            for ratio in [1.2, 1.5, 2.0, 2.5]:
                templates.append(
                    AlgorithmTemplate(
                        id=f"volume_price_confirm_{period}_{str(ratio).replace('.', '_')}",
                        name=f"量价·{period}日量比>{ratio}",
                        category="量价",
                        description=f"量比与价格方向确认，识别放量上涨/放量下跌。",
                        weight=0.034,
                        params={"kind": "volume_price", "period": period, "ratio": ratio},
                        tier="strong" if period == 20 and ratio in {1.5, 2.0} else "standard",
                    )
                )
        for pe in [15, 25, 35, 50, 80, 120]:
            templates.append(
                AlgorithmTemplate(
                    id=f"valuation_pe_guard_{pe}",
                    name=f"估值·PE阈值{pe}",
                    category="估值",
                    description=f"PE 低于/高于 {pe} 时的估值安全边际检查。",
                    weight=0.026,
                    params={"kind": "pe_guard", "pe": pe},
                )
            )
        for pb in [1, 2, 3, 5, 8, 12]:
            templates.append(
                AlgorithmTemplate(
                    id=f"valuation_pb_guard_{pb}",
                    name=f"估值·PB阈值{pb}",
                    category="估值",
                    description=f"PB 低于/高于 {pb} 时的资产估值检查。",
                    weight=0.024,
                    params={"kind": "pb_guard", "pb": pb},
                )
            )
        for threshold in [35, 45, 55, 65, 75]:
            templates.append(
                AlgorithmTemplate(
                    id=f"news_reliability_{threshold}",
                    name=f"新闻·可靠度阈值{threshold}",
                    category="新闻",
                    description="新闻证据可靠度和风险词对方向的影响。",
                    weight=0.026,
                    params={"kind": "news_reliability", "threshold": threshold},
                )
            )
        for threshold in [8, 12, 15, 20, 25, 30]:
            templates.append(
                AlgorithmTemplate(
                    id=f"risk_guard_drawdown_{threshold}",
                    name=f"风控·回撤阈值{threshold}%",
                    category="风控",
                    description=f"近 60 日最大回撤超过 {threshold}% 时触发防守。",
                    weight=0.04,
                    params={"kind": "risk_drawdown", "threshold": -threshold / 100},
                    tier="strong" if threshold in {12, 15, 20} else "standard",
                )
            )
        for threshold in [5, 8, 10, 15, 20, 25]:
            templates.append(
                AlgorithmTemplate(
                    id=f"holding_stop_review_{threshold}",
                    name=f"持仓·亏损复核{threshold}%",
                    category="持仓",
                    description=f"持仓亏损达到 {threshold}% 时触发减仓/复核。",
                    weight=0.025,
                    params={"kind": "holding_stop", "threshold": -threshold / 100},
                )
            )
        for count in [1, 2, 3, 4, 5, 8]:
            templates.append(
                AlgorithmTemplate(
                    id=f"memory_failure_penalty_{count}",
                    name=f"记忆·失败样本惩罚{count}",
                    category="记忆",
                    description=f"历史失败记忆达到 {count} 条时降低进攻评分。",
                    weight=0.02,
                    params={"kind": "memory_failure", "count": count},
                )
            )
        return templates

    def _run_template(self, ctx: dict[str, Any], template: AlgorithmTemplate) -> dict[str, Any]:
        kind = template.params.get("kind")
        if kind == "trend_ma":
            return self._algo_trend_ma(ctx, template)
        if kind == "ma_cross":
            return self._algo_ma_cross(ctx, template)
        if kind == "return_momentum":
            return self._algo_return_momentum(ctx, template)
        if kind == "rsi_band":
            return self._algo_rsi_band(ctx, template)
        if kind == "drawdown_reversion":
            return self._algo_drawdown_reversion(ctx, template)
        if kind == "ma_distance":
            return self._algo_ma_distance(ctx, template)
        if kind == "volatility_guard":
            return self._algo_volatility_guard(ctx, template)
        if kind == "volume_price":
            return self._algo_volume_price(ctx, template)
        if kind == "pe_guard":
            return self._algo_pe_guard(ctx, template)
        if kind == "pb_guard":
            return self._algo_pb_guard(ctx, template)
        if kind == "news_reliability":
            return self._algo_news_reliability(ctx, template)
        if kind == "risk_drawdown":
            return self._algo_risk_drawdown(ctx, template)
        if kind == "holding_stop":
            return self._algo_holding_stop(ctx, template)
        if kind == "memory_failure":
            return self._algo_memory_failure(ctx, template)
        return {"score": 50, "view": kind or "generated", "direction": "neutral", "position_bias": 0, "reasons": ["未知参数化算法。"], "risks": []}

    def _algo_trend_ma(self, ctx: dict[str, Any], template: AlgorithmTemplate) -> dict[str, Any]:
        p, t = template.params, ctx["technical"]
        window = p["window"]
        ma = _metric(t, f"ma{window}")
        price = _metric(t, "current_price")
        if ma is None or price is None:
            return _neutral(template, "均线或价格数据不足。")
        distance = price / ma - 1
        score = 50 + distance * 260
        if distance > p["buffer"]:
            score += 12
        if distance < -p["buffer"]:
            score -= 16
        return _result(template, score, [f"价格相对 MA{window} 偏离 {distance:.2%}，缓冲阈值 {p['buffer']:.1%}。"], ["跌破关键均线会削弱趋势。"])

    def _algo_ma_cross(self, ctx: dict[str, Any], template: AlgorithmTemplate) -> dict[str, Any]:
        p, t = template.params, ctx["technical"]
        fast = _metric(t, f"ma{p['fast']}")
        slow = _metric(t, f"ma{p['slow']}")
        if fast is None or slow is None:
            return _neutral(template, "均线结构数据不足。")
        spread = fast / slow - 1
        score = 50 + spread * 320
        if spread > p["margin"]:
            score += 10
        if spread < -p["margin"]:
            score -= 14
        return _result(template, score, [f"MA{p['fast']} 相对 MA{p['slow']} 乖离 {spread:.2%}。"], ["短均线下穿长均线时趋势转弱。"])

    def _algo_return_momentum(self, ctx: dict[str, Any], template: AlgorithmTemplate) -> dict[str, Any]:
        p, t = template.params, ctx["technical"]
        ret = _metric(t, f"ret{p['period']}", 0)
        score = 50 + ret * 180
        risks = []
        if ret > p["threshold"] * 2:
            score -= 8
            risks.append("涨幅显著超过阈值，追高风险增加。")
        if ret < -p["threshold"]:
            score -= 18
            risks.append("阶段收益跌破负阈值，动量转弱。")
        return _result(template, score, [f"近 {p['period']} 日收益 {ret:.2%}，阈值 {p['threshold']:.1%}。"], risks)

    def _algo_rsi_band(self, ctx: dict[str, Any], template: AlgorithmTemplate) -> dict[str, Any]:
        p, t = template.params, ctx["technical"]
        rsi = _metric(t, "rsi")
        if rsi is None:
            return _neutral(template, "RSI 数据不足。")
        score = 58 if p["low"] <= rsi <= p["high"] else 42
        risks = []
        if rsi > p["high"]:
            score -= min(20, (rsi - p["high"]) * 0.8)
            risks.append("RSI 高于区间上沿，短线过热。")
        if rsi < p["low"]:
            score += min(12, (p["low"] - rsi) * 0.5)
            risks.append("RSI 低于区间下沿，可能是超跌也可能是弱势延续。")
        return _result(template, score, [f"RSI {rsi:.1f}，目标区间 {p['low']}-{p['high']}。"], risks)

    def _algo_drawdown_reversion(self, ctx: dict[str, Any], template: AlgorithmTemplate) -> dict[str, Any]:
        p, t = template.params, ctx["technical"]
        dd = _metric(t, "max_drawdown", 0)
        trend = _metric(t, "trend_score", 50)
        score = 50
        reasons = [f"近期最大回撤 {dd:.2%}，触发阈值 {p['drawdown']:.1%}。"]
        risks = ["超跌修复需要趋势确认。"]
        if dd <= p["drawdown"] and trend >= 48:
            score += 14
        elif dd <= p["drawdown"] and trend < 48:
            score -= 8
            risks.append("回撤较深且趋势分偏低，可能不是修复而是破位。")
        return _result(template, score, reasons, risks)

    def _algo_ma_distance(self, ctx: dict[str, Any], template: AlgorithmTemplate) -> dict[str, Any]:
        p, t = template.params, ctx["technical"]
        price = _metric(t, "current_price")
        ma = _metric(t, f"ma{p['ma']}")
        if price is None or ma is None:
            return _neutral(template, "价格或均线数据不足。")
        dist = price / ma - 1
        score = 50
        risks = []
        if dist <= -p["distance"]:
            score += 10 if _metric(t, "trend_score", 50) >= 50 else -8
            risks.append("负偏离可能带来修复，也可能是趋势破位。")
        elif dist >= p["distance"]:
            score -= 8
            risks.append("正偏离过大，短线回撤风险增加。")
        return _result(template, score, [f"相对 MA{p['ma']} 偏离 {dist:.2%}，阈值 {p['distance']:.1%}。"], risks)

    def _algo_volatility_guard(self, ctx: dict[str, Any], template: AlgorithmTemplate) -> dict[str, Any]:
        vol = _metric(ctx["technical"], "volatility")
        if vol is None:
            return _neutral(template, "波动率数据不足。")
        threshold = template.params["threshold"]
        score = 62 if vol <= threshold else 48 - min(20, (vol - threshold) * 80)
        risks = ["波动率过高会降低仓位承受度。"] if vol > threshold else []
        return _result(template, score, [f"年化波动 {vol:.2%}，阈值 {threshold:.0%}。"], risks)

    def _algo_volume_price(self, ctx: dict[str, Any], template: AlgorithmTemplate) -> dict[str, Any]:
        p, t = template.params, ctx["technical"]
        vr = _metric(t, "volume_ratio")
        ret5 = _metric(t, "ret5", 0)
        if vr is None:
            return _neutral(template, "量比数据不足。")
        score = 52
        risks = []
        if vr >= p["ratio"] and ret5 > 0:
            score += 14
        if vr >= p["ratio"] and ret5 < 0:
            score -= 22
            risks.append("放量下跌，资金面转弱。")
        return _result(template, score, [f"量比 {vr:.2f}，近 5 日收益 {ret5:.2%}，阈值 {p['ratio']}。"], risks)

    def _algo_pe_guard(self, ctx: dict[str, Any], template: AlgorithmTemplate) -> dict[str, Any]:
        pe = _metric(ctx["fundamental"], "pe")
        threshold = template.params["pe"]
        if pe is None:
            return _neutral(template, "PE 数据不足。")
        score = 60 if 0 < pe <= threshold else 42 if pe > threshold else 50
        risks = [f"PE {pe:.1f} 高于阈值 {threshold}。"] if pe > threshold else []
        return _result(template, score, [f"PE {pe:.1f}，阈值 {threshold}。"], risks)

    def _algo_pb_guard(self, ctx: dict[str, Any], template: AlgorithmTemplate) -> dict[str, Any]:
        pb = _metric(ctx["fundamental"], "pb")
        threshold = template.params["pb"]
        if pb is None:
            return _neutral(template, "PB 数据不足。")
        score = 60 if 0 < pb <= threshold else 42 if pb > threshold else 50
        risks = [f"PB {pb:.1f} 高于阈值 {threshold}。"] if pb > threshold else []
        return _result(template, score, [f"PB {pb:.1f}，阈值 {threshold}。"], risks)

    def _algo_news_reliability(self, ctx: dict[str, Any], template: AlgorithmTemplate) -> dict[str, Any]:
        threshold = template.params["threshold"]
        evidence = ctx.get("news_evidence", [])
        sentiment = ctx.get("sentiment", {})
        if not evidence:
            return _neutral(template, "暂无新闻证据。")
        best = max(float(item.get("reliability_score") or 0) for item in evidence)
        risk_hits = sum(1 for item in evidence if item.get("risk_keywords"))
        score = sentiment.get("news_score", 50) + (8 if best >= threshold else -6) - min(18, risk_hits * 5)
        risks = [f"发现 {risk_hits} 条含风险词新闻。"] if risk_hits else []
        return _result(template, score, [f"最高可靠度 {best:.1f}，阈值 {threshold}。"], risks)

    def _algo_risk_drawdown(self, ctx: dict[str, Any], template: AlgorithmTemplate) -> dict[str, Any]:
        dd = _metric(ctx["technical"], "max_drawdown", 0)
        threshold = template.params["threshold"]
        score = 64 if dd > threshold else 35
        risks = [f"最大回撤 {dd:.2%} 触及阈值 {threshold:.1%}。"] if dd <= threshold else []
        return _result(template, score, [f"最大回撤 {dd:.2%}，阈值 {threshold:.1%}。"], risks)

    def _algo_holding_stop(self, ctx: dict[str, Any], template: AlgorithmTemplate) -> dict[str, Any]:
        holding = ctx.get("holding")
        if not holding:
            return _neutral(template, "未记录持仓。")
        profit = holding.get("profit_rate")
        if profit is None:
            return _neutral(template, "持仓收益不可得。")
        threshold = template.params["threshold"]
        score = 35 if profit <= threshold else 56
        risks = [f"持仓收益 {profit:.2%} 触及亏损复核阈值 {threshold:.1%}。"] if profit <= threshold else []
        return _result(template, score, [f"持仓收益 {profit:.2%}，阈值 {threshold:.1%}。"], risks)

    def _algo_memory_failure(self, ctx: dict[str, Any], template: AlgorithmTemplate) -> dict[str, Any]:
        count = template.params["count"]
        memories = ctx.get("memories", [])
        failures = [m for m in memories if m.get("outcome") == "failed" and m.get("status") != "ignored"]
        score = 40 if len(failures) >= count else 52
        risks = [f"历史失败样本 {len(failures)} 条，达到阈值 {count}。"] if len(failures) >= count else []
        return _result(template, score, [f"失败记忆 {len(failures)} 条，阈值 {count}。"], risks)

    def combine_results(self, results: list[dict[str, Any]], ctx: dict[str, Any]) -> dict[str, Any]:
        if not results:
            return {"overall_score": 50, "action": "uncertain", "confidence": 40, "position": "0%", "notes": ["未选择算法。"]}

        base_score = self._weighted_score(results)
        bullish = sum(1 for item in results if item.get("direction") == "bullish")
        bearish = sum(1 for item in results if item.get("direction") == "bearish")
        neutral = max(0, len(results) - bullish - bearish)
        consensus = max(bullish, bearish, neutral) / len(results)
        conflict_penalty = min(bullish, bearish) / len(results) * 14
        hard_risks = self._hard_risks(results, ctx)
        memory_penalty = self._memory_penalty(ctx)
        adjusted_score = clamp(base_score - conflict_penalty - memory_penalty)
        if hard_risks:
            adjusted_score = min(adjusted_score, 48)

        avg_position = sum(float(item.get("position_bias", 0)) * item.get("weight", 0) for item in results) / (sum(item.get("weight", 0) for item in results) or 1)
        if bearish > bullish:
            avg_position = min(avg_position, 0.08)
        if hard_risks:
            avg_position = 0

        action = self._action(adjusted_score, results)
        if hard_risks:
            action = "avoid" if not ctx.get("holding") else "reduce"
        elif bullish >= 2 and bearish == 0 and adjusted_score >= 66:
            action = "buy_candidate"
        elif bullish > bearish and adjusted_score >= 55:
            action = "watch"

        confidence = clamp(40 + consensus * 35 + abs(adjusted_score - 50) * 0.35 - conflict_penalty)
        notes = [
            f"多算法共识度 {consensus:.0%}，看多 {bullish}，看空 {bearish}，中性 {neutral}。",
            f"基础分 {base_score:.1f}，冲突惩罚 {conflict_penalty:.1f}，记忆惩罚 {memory_penalty:.1f}。",
        ]
        notes.extend(hard_risks[:3])
        return {
            "base_score": base_score,
            "overall_score": adjusted_score,
            "action": action,
            "confidence": confidence,
            "position": f"{avg_position:.0%}" if action in {"buy_candidate", "hold", "watch"} else "0%",
            "consensus": consensus,
            "bullish_votes": bullish,
            "bearish_votes": bearish,
            "neutral_votes": neutral,
            "conflict_penalty": conflict_penalty,
            "memory_penalty": memory_penalty,
            "hard_risks": hard_risks,
            "notes": notes,
        }

    def _normalize_result(self, result: dict[str, Any], algo: AnalysisAlgorithm) -> dict[str, Any]:
        score = clamp(float(result.get("score", 50)))
        direction = result.get("direction") or ("bullish" if score >= 62 else "bearish" if score < 42 else "neutral")
        return {
            **result,
            "id": algo.id,
            "name": algo.name,
            "weight": algo.weight,
            "score": score,
            "direction": direction,
            "position_bias": float(result.get("position_bias", _position_bias(score))),
        }

    def _hard_risks(self, results: list[dict[str, Any]], ctx: dict[str, Any]) -> list[str]:
        risk_text = " ".join(" ".join(item.get("risks", [])) for item in results)
        risks = []
        if any(key in risk_text for key in ["止损", "放量下跌", "高风险", "重大负面"]):
            risks.append("触发硬性风控：止损/放量下跌/高风险/重大负面之一。")
        risk = ctx.get("risk") or {}
        if risk.get("risk_level") == "high":
            risks.append("系统风险等级为 high，组合算法禁止强买入。")
        return risks

    def _memory_penalty(self, ctx: dict[str, Any]) -> float:
        memories = ctx.get("memories", [])
        open_failures = [m for m in memories if m.get("outcome") == "failed" and m.get("status") != "ignored"]
        return min(12.0, len(open_failures) * 3.0)

    def _weighted_score(self, results: list[dict[str, Any]]) -> float:
        if not results:
            return 50
        total_weight = sum(item["weight"] for item in results) or 1
        return clamp(sum(item["score"] * item["weight"] for item in results) / total_weight)

    def _action(self, score: float, results: list[dict[str, Any]]) -> str:
        risk_text = " ".join(" ".join(item.get("risks", [])) for item in results)
        if any(key in risk_text for key in ["止损", "放量下跌", "高风险"]):
            return "reduce"
        if score >= 72:
            return "buy_candidate"
        if score >= 58:
            return "watch"
        if score < 42:
            return "avoid"
        return "uncertain"

    def _confidence(self, score: float, results: list[dict[str, Any]]) -> float:
        dispersion = 0
        if results:
            avg = sum(item["score"] for item in results) / len(results)
            dispersion = sum(abs(item["score"] - avg) for item in results) / len(results)
        return clamp(45 + abs(score - 50) * 0.7 - dispersion * 0.2)

    def _summary(self, action: str, score: float, results: list[dict[str, Any]], decision: dict[str, Any] | None = None) -> str:
        top_risks = [risk for item in results for risk in item.get("risks", [])][:3]
        risk_text = "；".join(top_risks) if top_risks else "暂无明确高风险触发项。"
        if decision:
            return f"算法组合动作为 {action}，综合评分 {score:.1f}，建议仓位 {decision.get('position', '0%')}。主要风险：{risk_text}"
        return f"算法组合动作为 {action}，综合评分 {score:.1f}。主要风险：{risk_text}"

    def _holding(self, stock_code: str) -> dict[str, Any] | None:
        with session_scope() as session:
            holding = session.scalar(
                select(Holding)
                .where(Holding.stock_code == stock_code, Holding.status.in_(["holding", "partially_sold", "watching"]))
                .order_by(Holding.created_at.desc())
            )
            if not holding:
                return None
            current_price = StockDataService().get_latest_price(stock_code)
            profit_rate = None
            if current_price and holding.buy_price:
                profit_rate = (current_price - holding.buy_price) / holding.buy_price
            return {
                "id": holding.id,
                "buy_price": holding.buy_price,
                "current_quantity": holding.current_quantity,
                "profit_rate": profit_rate,
                "buy_reason": holding.buy_reason,
                "status": holding.status,
            }

    def _holding_profit_rate(self, stock_code: str) -> float | None:
        holding = self._holding(stock_code)
        return None if not holding else holding.get("profit_rate")

    def _memories(self, stock_code: str) -> list[dict[str, Any]]:
        with session_scope() as session:
            memories = list(
                session.scalars(
                    select(LearningMemory)
                    .where(LearningMemory.stock_code == stock_code)
                    .order_by(LearningMemory.created_at.desc())
                    .limit(20)
                )
            )
            return [
                {
                    "id": item.id,
                    "outcome": item.outcome,
                    "original_action": item.original_action,
                    "error_type": item.error_type,
                    "lesson": item.lesson,
                    "status": item.status,
                }
                for item in memories
            ]


def _position_bias(score: float) -> float:
    if score >= 78:
        return 0.30
    if score >= 68:
        return 0.22
    if score >= 58:
        return 0.14
    if score >= 50:
        return 0.06
    return 0.0


def _metric(data: dict[str, Any], key: str, default=None):
    value = data.get(key, default)
    try:
        if value is None:
            return default
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _result(template: AlgorithmTemplate, score: float, reasons: list[str], risks: list[str]) -> dict[str, Any]:
    score = clamp(score)
    direction = "bullish" if score >= 62 else "bearish" if score < 42 else "neutral"
    return {
        "score": score,
        "view": template.category,
        "direction": direction,
        "position_bias": _position_bias(score),
        "reasons": reasons,
        "risks": risks,
        "template_id": template.id,
        "tier": template.tier,
    }


def _neutral(template: AlgorithmTemplate, reason: str) -> dict[str, Any]:
    return {
        "score": 50,
        "view": template.category,
        "direction": "neutral",
        "position_bias": 0,
        "reasons": [reason],
        "risks": [],
        "template_id": template.id,
        "tier": template.tier,
    }
