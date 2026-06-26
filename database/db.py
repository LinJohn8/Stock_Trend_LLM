from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import get_settings


class Base(DeclarativeBase):
    pass


def _sqlite_url() -> str:
    settings = get_settings()
    if settings.database_url.startswith("sqlite:///"):
        db_path = settings.database_url.removeprefix("sqlite:///")
        path = Path(db_path)
        if not path.is_absolute():
            path = settings.root_dir / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"
    return settings.database_url


engine = create_engine(
    _sqlite_url(),
    connect_args={"check_same_thread": False} if _sqlite_url().startswith("sqlite") else {},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def init_db() -> None:
    from database import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()


def _ensure_sqlite_columns() -> None:
    if not _sqlite_url().startswith("sqlite"):
        return
    additions = {
        "stock_news_evidence": {
            "event_types": "TEXT DEFAULT '[]'",
            "extracted_entities": "TEXT DEFAULT '{}'",
        },
        "historical_simulations": {
            "fee_rate": "FLOAT DEFAULT 0.0003",
            "max_position": "FLOAT DEFAULT 0.85",
            "diagnostics_json": "TEXT DEFAULT '{}'",
            "ai_review": "TEXT DEFAULT ''",
        },
    }
    with engine.begin() as conn:
        for table, columns in additions.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}
            for column, definition in columns.items():
                if column not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    with session_scope() as session:
        yield session
