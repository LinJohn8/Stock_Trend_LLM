from __future__ import annotations


class TushareClient:
    """Reserved Tushare adapter. Fill token and endpoints when needed."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def is_configured(self) -> bool:
        return bool(self.token)
