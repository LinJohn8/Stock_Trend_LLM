from __future__ import annotations

from data_sources.akshare_client import AKShareClient


class IndexClient:
    def __init__(self) -> None:
        self.ak = AKShareClient()

    def get_hs300_daily(self):
        return self.ak.get_index_daily("sh000300")

    def get_shanghai_daily(self):
        return self.ak.get_index_daily("sh000001")

    def get_shenzhen_daily(self):
        return self.ak.get_index_daily("sz399001")

    def get_chinext_daily(self):
        return self.ak.get_index_daily("sz399006")
