from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from database.db import init_db
from services.scheduler_service import SchedulerService
from services.stock_data_service import StockDataService
from utils.logger import ensure_log_files, get_logger

logger = get_logger("app", "app.log")
scheduler_service = SchedulerService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_log_files()
    init_db()
    scheduler_service.start()
    logger.info("stock_ai_assistant started")
    try:
        yield
    finally:
        scheduler_service.shutdown()
        logger.info("stock_ai_assistant stopped")

app = FastAPI(
    title="stock_ai_assistant",
    description="本地 A 股 AI 辅助决策系统，仅用于研究和辅助复盘，不构成投资建议。",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/data-sources/{stock_code}")
def data_source_health(stock_code: str) -> dict:
    service = StockDataService()
    snapshot = service.get_market_snapshot(stock_code, refresh=False)
    quote = snapshot["quote"]
    return {
        "status": "ok",
        "stock_code": quote.get("stock_code"),
        "stock_name": quote.get("stock_name"),
        "quote_source": quote.get("source"),
        "current_price": quote.get("current_price"),
        "daily_rows": len(snapshot["daily"]),
        "weekly_rows": len(snapshot["weekly"]),
        "recent_5d_rows": len(snapshot["recent_5d"]),
        "intraday_rows": len(snapshot["intraday"]),
    }


@app.post("/tasks/daily")
def run_daily_job() -> dict[str, str]:
    scheduler_service.run_daily_job()
    return {"status": "started"}


if __name__ == "__main__":
    import uvicorn
    from config.settings import get_settings

    uvicorn.run("main:app", host="0.0.0.0", port=get_settings().api_preferred_port, reload=False)
