from __future__ import annotations

from ai.openai_provider import OpenAIProvider


class DeepSeekProvider(OpenAIProvider):
    def __init__(self) -> None:
        super().__init__(base_url="https://api.deepseek.com/v1")
