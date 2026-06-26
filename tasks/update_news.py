from __future__ import annotations

import argparse

from database.db import init_db
from services.news_ingestion_service import NewsIngestionService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stock_code")
    parser.add_argument("--name", default="")
    parser.add_argument("--keyword", action="append", default=[])
    args = parser.parse_args()
    init_db()
    items = NewsIngestionService().collect_for_stock(args.stock_code, args.name, args.keyword, limit=40)
    print({"stock_code": args.stock_code, "saved_evidence": len(items)})


if __name__ == "__main__":
    main()
