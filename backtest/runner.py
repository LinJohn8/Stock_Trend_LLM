from __future__ import annotations

from services.backtest_service import BacktestService


def main() -> None:
    service = BacktestService()
    updated = service.update_tracking()
    print(f"updated tracking rows: {updated}")
    print(service.stats())


if __name__ == "__main__":
    main()
