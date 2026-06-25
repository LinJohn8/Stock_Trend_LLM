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
