from __future__ import annotations

from database.db import init_db
from services.scheduler_service import SchedulerService


def main() -> None:
    init_db()
    SchedulerService().run_daily_job()


if __name__ == "__main__":
    main()
