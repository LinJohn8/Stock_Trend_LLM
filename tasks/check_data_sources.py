from __future__ import annotations

import argparse
from collections import Counter
from time import perf_counter

from database.db import init_db
from data_sources.news_client import NewsClient
from services.stock_data_service import StockDataService


def main() -> None:
    parser = argparse.ArgumentParser(description="Check real data-source availability for a stock.")
    parser.add_argument("stock_code", nargs="?", default="600519")
    parser.add_argument("--name", default="")
    parser.add_argument("--news-limit", type=int, default=5)
    args = parser.parse_args()

    init_db()
    service = StockDataService()
    started = perf_counter()
    snapshot = service.get_market_snapshot(args.stock_code, refresh=True)
    quote = snapshot["quote"]
    news = NewsClient().get_stock_news(
        args.stock_code,
        args.name or quote.get("stock_name", ""),
        limit=args.news_limit,
        topic_scope=["stock"],
    )

    print("Data source check")
    print(f"  Stock: {quote.get('stock_code')} {quote.get('stock_name') or args.name or ''}")
    print(f"  Quote: {quote.get('current_price')} from {quote.get('source', 'unknown')}")
    print(f"  Daily rows: {len(snapshot['daily'])}")
    if not snapshot["daily"].empty:
        print(f"  Daily range: {snapshot['daily']['date'].min()} -> {snapshot['daily']['date'].max()}")
    print(f"  Weekly rows: {len(snapshot['weekly'])}")
    print(f"  Recent 5D rows: {len(snapshot['recent_5d'])}")
    print(f"  Intraday rows: {len(snapshot['intraday'])}")
    print(f"  News fetched: {len(news)}")
    if news:
        source_counts = Counter(str(item.get("source") or "unknown") for item in news)
        print(f"  News sources: {dict(source_counts)}")
    print(f"  Elapsed: {perf_counter() - started:.2f}s")
    if news:
        print("  Top news:")
        for item in news[:3]:
            print(f"    - [{item['source']}] {item['title']}")


if __name__ == "__main__":
    main()
