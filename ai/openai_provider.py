from __future__ import annotations

import requests

from ai.base_provider import AIProvider
from config.settings import get_settings


class OpenAIProvider(AIProvider):
    """OpenAI-compatible chat completions provider."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ai_base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or settings.ai_api_key
        self.model = model or settings.ai_model

    def complete(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("AI_API_KEY 未配置")
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是保守、可解释的 A 股研究辅助系统。只输出用户要求的格式。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            },
            timeout=45,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
