from __future__ import annotations

import argparse

from database.db import init_db
from services.backtest_service import BacktestService
from services.memory_service import MemoryService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-success", action="store_true", help="also record successful signals")
    args = parser.parse_args()
    init_db()
    tracking = BacktestService().update_tracking()
    memories = MemoryService().generate_learning_memories(include_success=args.include_success)
    print({"tracking_updated": tracking, "learning_memories_updated": memories})


if __name__ == "__main__":
    main()
