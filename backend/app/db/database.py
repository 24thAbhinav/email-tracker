# database.py - DB engine, SessionLocal, Base

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from dotenv import load_dotenv
from sqlmodel import Session, SQLModel, create_engine

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./job_tracker.db")

# SQLAlchemy 2.0 requires postgresql:// instead of postgres://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_connect_args = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(DATABASE_URL, echo=False, connect_args=_connect_args)


def create_db_and_tables() -> None:
    """Create all tables registered on SQLModel metadata."""
    if DATABASE_URL.startswith("sqlite:///"):
        db_raw = DATABASE_URL.replace("sqlite:////", "/").replace("sqlite:///", "")
        if "/" in db_raw:
            Path(db_raw).parent.mkdir(parents=True, exist_ok=True)
    # Import models so they are registered on SQLModel.metadata before create_all.
    from app.db import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    with Session(engine) as session:
        yield session
