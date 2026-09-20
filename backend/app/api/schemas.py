# schemas.py - API response models

from __future__ import annotations

from datetime import datetime

from sqlmodel import SQLModel

from app.db.models import ApplicationStatus


class ApplicationRead(SQLModel):
    id: int
    company: str
    role: str
    status: ApplicationStatus
    applied_at: datetime | None = None
    updated_at: datetime
    source_email_id: str
    sender_email: str | None = None
    notes: str | None = None
    action_url: str | None = None
    event_date: str | None = None
    is_closed: bool = False
    closed_at: datetime | None = None


class ApplicationUpdate(SQLModel):
    is_closed: bool | None = None
    status: ApplicationStatus | None = None
    notes: str | None = None


class ApplicationStats(SQLModel):
    total: int  # excludes closed
    closed: int
    by_status: dict[str, int]


class ApplicationListResponse(SQLModel):
    items: list[ApplicationRead]
    total: int
    limit: int
    offset: int


class ApplicationEventRead(SQLModel):
    id: int
    application_id: int
    status: ApplicationStatus
    note: str | None = None
    action_url: str | None = None
    event_date: str | None = None
    created_at: datetime
