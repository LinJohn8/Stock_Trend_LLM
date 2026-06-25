from __future__ import annotations

from data_sources.akshare_client import AKShareClient


class IndustryClient:
    def __init__(self) -> None:
        self.ak = AKShareClient()

    def get_boards(self):
        return self.ak.get_industry_board()
