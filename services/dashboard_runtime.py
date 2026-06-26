from __future__ import annotations

from database.db import init_db
from services.scheduler_service import SchedulerService
from utils.logger import ensure_log_files, get_logger

logger = get_logger("app", "app.log")


class DashboardRuntime:
    """Start app services that should live with the Streamlit dashboard process."""

    def __init__(self) -> None:
        ensure_log_files()
        init_db()
        from config.settings import get_settings

        self.scheduler = None
        if get_settings().enable_dashboard_scheduler:
            self.scheduler = SchedulerService()
            self.scheduler.start()
        logger.info("dashboard runtime started")


def start_dashboard_runtime() -> DashboardRuntime:
    return DashboardRuntime()
