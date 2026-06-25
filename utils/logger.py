from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.settings import get_settings


_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(name: str = "app", filename: str | None = None) -> logging.Logger:
    """Create a rotating file logger plus console logging."""
    if name in _LOGGERS:
        return _LOGGERS[name]

    settings = get_settings()
    log_file = settings.logs_dir / (filename or f"{name}.log")
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    if not logger.handlers:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    _LOGGERS[name] = logger
    return logger


def ensure_log_files() -> None:
    for filename in [
        "app.log",
        "scheduler.log",
        "email.log",
        "data_fetch.log",
        "ai_analysis.log",
    ]:
        Path(get_settings().logs_dir / filename).touch(exist_ok=True)
