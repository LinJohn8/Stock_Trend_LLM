from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai.deepseek_provider import DeepSeekProvider
from ai.glm_provider import GLMProvider
from ai.openai_provider import OpenAIProvider
from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger("ai_analysis", "ai_analysis.log")

VALID_ACTIONS = {"watch", "buy_candidate", "hold", "reduce", "sell", "avoid", "uncertain"}


class AIAnalysisService:
    """Optional AI text refinement with strict JSON validation."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def analyze_single_stock(self, context: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.ai_enabled:
            return context
        try:
            prompt = self._render_prompt("single_stock_analysis_prompt.md", context)
            raw = self._provider().complete(prompt)
            parsed = self._parse_json(raw)
            return self._validate(parsed, fallback=context)
        except Exception as exc:
            logger.exception("AI single stock analysis failed: %s", exc)
            return context

    def review_holding(self, context: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.ai_enabled:
            return context
        try:
            prompt = self._render_prompt("holding_review_prompt.md", context)
            raw = self._provider().complete(prompt)
            parsed = self._parse_json(raw)
            return self._validate(parsed, fallback=context)
        except Exception as exc:
            logger.exception("AI holding review failed: %s", exc)
            return context

    def complete_skill_review(self, prompt_template: str, context: dict[str, Any]) -> str:
        """Run a free-form LLM skill review with computed context."""
        if not self.settings.ai_enabled:
            return _local_skill_fallback(context)
        try:
            prompt = prompt_template.replace("{{CONTEXT_JSON}}", json.dumps(context, ensure_ascii=False, default=str))
            return self._provider().complete(prompt)
        except Exception as exc:
            logger.exception("AI skill review failed: %s", exc)
            return _local_skill_fallback(context)

    def chat_about_stock(self, question: str, context: dict[str, Any]) -> str:
        """Answer a dashboard chat question using the current computed stock context."""
        if not self.settings.ai_enabled:
            return _local_stock_chat(question, context)
        try:
            prompt = (
                "你是一个保守、可解释的 A 股研究辅助系统。"
                "只能基于给定 JSON 上下文回答，不要承诺收益，不要给出自动交易指令。"
                "回答应包含：结论、证据、风险、下一步观察。\n\n"
                f"用户问题：{question}\n\n"
                f"上下文 JSON：{json.dumps(context, ensure_ascii=False, default=str)}"
            )
            return self._provider().complete(prompt)
        except Exception as exc:
            logger.exception("AI stock chat failed: %s", exc)
            return _local_stock_chat(question, context)

    def review_simulation(self, context: dict[str, Any]) -> str:
        """Review a historical simulation result and diagnostics."""
        if not self.settings.ai_enabled:
            return _local_simulation_review(context)
        try:
            prompt = (
                "你是一个保守的历史模拟复盘助手。请基于 JSON 输出：模拟结论、交易是否被资金/一手限制阻塞、"
                "哪些算法有数据或执行问题、哪些结果不可靠、下一步应该检查什么。不要承诺收益。\n\n"
                f"上下文 JSON：{json.dumps(context, ensure_ascii=False, default=str)}"
            )
            return self._provider().complete(prompt)
        except Exception as exc:
            logger.exception("AI simulation review failed: %s", exc)
            return _local_simulation_review(context)

    def _provider(self):
        if self.settings.ai_provider == "openai":
            return OpenAIProvider()
        if self.settings.ai_provider == "glm":
            return GLMProvider()
        return DeepSeekProvider()

    def _render_prompt(self, name: str, context: dict[str, Any]) -> str:
        path = Path(__file__).resolve().parents[1] / "ai" / "prompts" / name
        template = path.read_text(encoding="utf-8")
        return template.replace("{{CONTEXT_JSON}}", json.dumps(context, ensure_ascii=False, default=str))

    def _parse_json(self, raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.removeprefix("json").strip()
        return json.loads(text)

    def _validate(self, data: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        action = data.get("action")
        if action not in VALID_ACTIONS:
            data["action"] = "uncertain"
        data["confidence"] = max(0, min(100, float(data.get("confidence", fallback.get("confidence", 50)))))
        data["overall_score"] = max(0, min(100, float(data.get("overall_score", fallback.get("overall_score", 50)))))
        for key in ["risk_points", "buy_conditions", "sell_conditions", "hold_conditions", "invalidation_conditions"]:
            if key in data and not isinstance(data[key], list):
                data[key] = [str(data[key])]
        return {**fallback, **data}


def _local_skill_fallback(context: dict[str, Any]) -> str:
    signal = context.get("latest_signal") or {}
    technical = context.get("technical") or {}
    risk = context.get("risk") or {}
    return (
        "AI 未启用或调用失败，以下为本地计算摘要：\n"
        f"- 动作：{signal.get('action', 'uncertain')}，综合评分：{signal.get('overall_score', '-')}\n"
        f"- 技术摘要：{technical.get('technical_summary', '暂无')}\n"
        f"- 风险等级：{risk.get('risk_level', 'unknown')}，风险点：{risk.get('risk_points', [])}\n"
        "- 请仅将该结果作为研究和复盘材料，不构成投资建议。"
    )


def _local_stock_chat(question: str, context: dict[str, Any]) -> str:
    quote = context.get("quote") or {}
    signal = context.get("signal") or context.get("latest_signal") or {}
    algorithm = context.get("algorithm") or {}
    sentiment = context.get("sentiment") or {}
    news = context.get("news_evidence") or []
    technical = context.get("technical") or {}
    top_news = "；".join(str(item.get("title", "")) for item in news[:3]) or "暂无已保存新闻证据"
    return (
        f"基于当前页面已有数据，我对“{question}”的本地回答如下：\n\n"
        f"结论：{quote.get('stock_code', '-') } {quote.get('stock_name', '')} 当前更适合按“{signal.get('action', algorithm.get('action', 'watch'))}”观察，"
        f"综合评分约 {signal.get('overall_score', algorithm.get('overall_score', '-'))}。\n\n"
        f"证据：最新价 {quote.get('current_price', '-')}，涨跌幅 {quote.get('pct_change', '-')}%；"
        f"技术评分 {technical.get('trend_score', '-')}，消息面评分 {sentiment.get('news_score', '-')}。"
        f"主要新闻：{top_news}。\n\n"
        f"风险：{signal.get('risk_points', algorithm.get('combination', {}).get('hard_risks', ['暂无明确高风险触发项']))}。\n\n"
        "下一步观察：重点看价格是否跌破 MA20、是否出现放量下跌、是否有重大公告/政策变化，并把实际交易决策留给人工确认。"
    )


def _local_simulation_review(context: dict[str, Any]) -> str:
    summary = context.get("summary") or {}
    diagnostics = context.get("diagnostics") or {}
    algos = diagnostics.get("algorithms", {})
    problem_algos = [
        f"{item.get('name', algo_id)}：warnings={item.get('warnings', 0)}, errors={item.get('errors', 0)}"
        for algo_id, item in algos.items()
        if item.get("warnings", 0) or item.get("errors", 0)
    ][:8]
    blockers = diagnostics.get("trade_blockers", [])[:5]
    return (
        "本地模拟复盘：\n"
        f"- 最终收益：{summary.get('final_return', 0):.2%}，基准收益：{summary.get('benchmark_return') if summary.get('benchmark_return') is not None else '-'}，"
        f"最大回撤：{summary.get('max_drawdown', 0):.2%}，交易次数：{summary.get('trade_count', 0)}。\n"
        f"- 数据诊断：{diagnostics.get('data', {})}。\n"
        f"- 算法问题：{'；'.join(problem_algos) if problem_algos else '未发现算法执行错误或明显数据不足。'}\n"
        f"- 交易阻塞：{'；'.join(item.get('message', '') for item in blockers) if blockers else '未记录资金/一手限制阻塞。'}\n"
        "- 解释：如果初始资金低于一手成本，系统仍会展示股票走势与算法信号，但不会产生真实买入交易。"
    )
