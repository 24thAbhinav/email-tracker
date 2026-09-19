# models.py - SQLAlchemy ORM models / Pydantic schemas

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


class ApplicationStatus(str, Enum):
    APPLIED = "APPLIED"
    UNDER_REVIEW = "UNDER_REVIEW"
    OA = "OA"
    INTERVIEW = "INTERVIEW"
    INTERVIEW_PASSED = "INTERVIEW_PASSED"
    INTERVIEW_REJECTED = "INTERVIEW_REJECTED"
    OFFER = "OFFER"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class Application(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)

    company: str = Field(index=True)
    role: str = Field(index=True)
    status: ApplicationStatus

    applied_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"onupdate": utcnow},
    )

    source_email_id: str = Field(unique=True, index=True)
