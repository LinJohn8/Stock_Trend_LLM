from __future__ import annotations

from fastapi import FastAPI

from database.db import init_db
from services.scheduler_service import SchedulerService
from utils.logger import ensure_log_files, get_logger

logger = get_logger("app", "app.log")

app = FastAPI(
    title="stock_ai_assistant",
    description="本地 A 股 AI 辅助决策系统，仅用于研究和辅助复盘，不构成投资建议。",
    version="0.1.0",
)
scheduler_service = SchedulerService()


@app.on_event("startup")
def startup() -> None:
    ensure_log_files()
    init_db()
    scheduler_service.start()
    logger.info("stock_ai_assistant started")


@app.on_event("shutdown")
def shutdown() -> None:
    scheduler_service.shutdown()
    logger.info("stock_ai_assistant stopped")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tasks/daily")
def run_daily_job() -> dict[str, str]:
    scheduler_service.run_daily_job()
    return {"status": "started"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
