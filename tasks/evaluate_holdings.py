from __future__ import annotations

from database.db import init_db
from services.holding_service import HoldingService


def main() -> None:
    init_db()
    service = HoldingService()
    for holding in service.list_holdings(active_only=True):
        snap = service.snapshot_holding(holding)
        if snap:
            print(f"{holding.stock_code} profit={snap.profit_rate:.2%} risk={snap.risk_level}")


if __name__ == "__main__":
    main()
