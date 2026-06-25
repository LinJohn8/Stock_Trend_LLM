from __future__ import annotations

import argparse

from database.db import init_db
from services.stock_data_service import StockDataService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stock_code")
    args = parser.parse_args()
    init_db()
    rows = StockDataService().update_daily_data(args.stock_code)
    print(f"updated {args.stock_code}: {rows} rows")


if __name__ == "__main__":
    main()
