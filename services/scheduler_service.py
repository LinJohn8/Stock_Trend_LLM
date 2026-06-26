from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

from config.settings import get_settings
from database.db import init_db
from services.email_service import EmailService
from services.holding_service import HoldingService
from services.portfolio_service import PortfolioService
from services.signal_service import SignalService
from services.stock_data_service import StockDataService
from services.backtest_service import BacktestService
from services.memory_service import MemoryService
from services.news_ingestion_service import NewsIngestionService
from utils.logger import get_logger

logger = get_logger("scheduler", "scheduler.log")


class SchedulerService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.scheduler = BackgroundScheduler(timezone=ZoneInfo(self.settings.email_timezone))

    def start(self) -> None:
        if self.scheduler.running:
            return
        for send_time in self.settings.email_send_time_list:
            hour, minute = [int(x) for x in send_time.split(":")]
            self.scheduler.add_job(
                self.run_daily_job,
                CronTrigger(hour=hour, minute=minute, timezone=ZoneInfo(self.settings.email_timezone)),
                id=f"daily_stock_report_{send_time.replace(':', '')}",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=3600,
            )
        self.scheduler.start()
        logger.info("scheduler started daily=%s", ",".join(self.settings.email_send_time_list))

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def run_daily_job(self) -> list[dict]:
        init_db()
        logger.info("daily job started")
        signals: list[dict] = []
        try:
            data_service = StockDataService()
            signal_service = SignalService()
            holding_service = HoldingService()

            holdings = holding_service.list_holdings(active_only=True)
            watchlist = PortfolioService().list_watchlist(active_only=True)
            codes = {h.stock_code: h.stock_name for h in holdings}
            for w in watchlist:
                codes.setdefault(w.stock_code, w.stock_name)

            for code, name in codes.items():
                data_service.update_daily_data(code)
                if self.settings.enable_news_analysis:
                    NewsIngestionService().collect_for_stock(code, name, limit=20)
                holding = next((h for h in holdings if h.stock_code == code), None)
                profit_rate = None
                if holding:
                    snap = holding_service.snapshot_holding(holding)
                    profit_rate = snap.profit_rate if snap else None
                signal = signal_service.analyze_stock(code, name, is_holding=holding is not None, holding_profit_rate=profit_rate)
                signals.append(signal)
                logger.info("analyzed %s action=%s score=%.1f", code, signal["action"], signal["overall_score"])

            BacktestService().update_tracking()
            MemoryService().generate_learning_memories()
            EmailService().send_daily_report()
            logger.info("daily job finished signals=%s", len(signals))
        except Exception as exc:
            logger.exception("daily job failed: %s", exc)
        return signals
