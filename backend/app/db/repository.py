# repository.py - persistence layer for job applications

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db.models import Application, ApplicationEvent, ApplicationStatus, utcnow


@runtime_checkable
class ApplicationExtractionLike(Protocol):
    """Structural type for anything carrying extracted application data.

    Decouples the repository from the LLM/Pydantic extraction model so the
    LangGraph layer can pass its own ApplicationExtraction instance.
    """

    company: str
    role: str
    status: ApplicationStatus
    summary: str | None = None
    action_url: str | None = None
    event_date: str | None = None


class ApplicationRepository:
    """Database operations for :class:.

    This layer contains no LLM, LangGraph, or Gmail logic. It only persists
    and retrieves application records using the provided SQLModel session.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_application(
        self,
        company: str,
        role: str,
        status: ApplicationStatus,
        source_email_id: str,
        applied_at: datetime | None = None,
        sender_email: str | None = None,
        notes: str | None = None,
        action_url: str | None = None,
        event_date: str | None = None,
    ) -> Application:
        """Insert a new application. Raises IntegrityError on duplicate email."""
        application = Application(
            company=company,
            role=role,
            status=status,
            source_email_id=source_email_id,
            applied_at=applied_at,
            sender_email=sender_email,
            notes=notes,
            action_url=action_url,
            event_date=event_date,
        )
        self.session.add(application)
        try:
            self.session.flush()  # assign id before recording the event
            self._record_event(
                application,
                status,
                note=notes,
                action_url=action_url,
                event_date=event_date,
            )
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise
        self.session.refresh(application)
        return application

    def get_application_by_id(self, application_id: int) -> Application | None:
        return self.session.get(Application, application_id)

    def get_application_by_email_id(self, source_email_id: str) -> Application | None:
        statement = select(Application).where(
            Application.source_email_id == source_email_id
        )
        return self.session.exec(statement).first()

    def find_application_by_company_and_role(
        self, company: str, role: str
    ) -> Application | None:
        """Match an existing application using normalized company + role.

        Matching is case-insensitive and whitespace-insensitive. This is the
        single place to change if the strategy is improved later.
        """
        statement = select(Application).where(
            func.lower(func.trim(Application.company)) == company.strip().lower(),
            func.lower(func.trim(Application.role)) == role.strip().lower(),
        )
        return self.session.exec(statement).first()

    def update_application_status(
        self,
        application: Application,
        status: ApplicationStatus,
        notes: str | None = None,
        action_url: str | None = None,
        event_date: str | None = None,
    ) -> Application:
        """Update an application's status and touch updated_at."""
        application.status = status
        application.updated_at = utcnow()
        if notes:
            application.notes = notes
        if action_url:
            application.action_url = action_url
        if event_date:
            application.event_date = event_date
        self.session.add(application)
        self._record_event(
            application,
            status,
            note=notes,
            action_url=action_url,
            event_date=event_date,
        )
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise
        self.session.refresh(application)
        return application

    def set_application_closed(
        self, application: Application, is_closed: bool
    ) -> Application:
        """Close an application (status -> CLOSED) or reopen it.

        Closing records the previous status so reopening restores it.
        """
        if is_closed:
            if not application.is_closed:
                application.previous_status = application.status
            application.status = ApplicationStatus.CLOSED
            application.is_closed = True
            application.closed_at = utcnow()
        else:
            application.status = application.previous_status or ApplicationStatus.APPLIED
            application.previous_status = None
            application.is_closed = False
            application.closed_at = None
        application.updated_at = utcnow()
        self.session.add(application)
        self._record_event(application, application.status)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise
        self.session.refresh(application)
        return application

    def status_counts(self) -> dict[ApplicationStatus, int]:
        """Count applications per status (closed included)."""
        rows = self.session.exec(
            select(Application.status, func.count()).group_by(Application.status)
        ).all()
        counts = {status: 0 for status in ApplicationStatus}
        for status, count in rows:
            counts[status] = count
        return counts

    def list_applications(
        self,
        *,
        status: ApplicationStatus | None = None,
        company: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_closed: bool = True,
    ) -> tuple[list[Application], int]:
        """Return ``(items, total)`` ordered by most recently updated."""
        conditions = []
        if not include_closed:
            conditions.append(Application.is_closed.is_(False))
        if status is not None:
            conditions.append(Application.status == status)
        if company:
            conditions.append(
                func.lower(func.trim(Application.company)) == company.strip().lower()
            )
        if search:
            term = f"%{search.strip().lower()}%\草" if False else f"%{search.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(Application.company).like(term),
                    func.lower(Application.role).like(term),
                )
            )

        total = self.session.exec(
            select(func.count()).select_from(Application).where(*conditions)
        ).one()
        statement = (
            select(Application)
            .where(*conditions)
            .order_by(Application.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = list(self.session.exec(statement).all())
        return items, total

    def list_events(self, application_id: int) -> list[ApplicationEvent]:
        """Return an application's status history, oldest first."""
        statement = (
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == application_id)
            .order_by(ApplicationEvent.created_at.asc(), ApplicationEvent.id.asc())
        )
        return list(self.session.exec(statement).all())

    def _record_event(
        self,
        application: Application,
        status: ApplicationStatus,
        note: str | None = None,
        action_url: str | None = None,
        event_date: str | None = None,
    ) -> None:
        self.session.add(
            ApplicationEvent(
                application_id=application.id,
                status=status,
                note=note,
                action_url=action_url,
                event_date=event_date,
            )
        )

    def create_or_update_application(
        self,
        extraction: ApplicationExtractionLike,
        email_id: str,
        sender_email: str | None = None,
        applied_at: datetime | None = None,
    ) -> Application:
        """Idempotently persist an extracted application.

        - The same email_id never creates a second record.
        - A different email for the same company + role updates the
          existing application instead of creating another one.
        """
        existing_by_email = self.get_application_by_email_id(email_id)
        if existing_by_email is not None:
            if existing_by_email.applied_at is None and applied_at is not None:
                existing_by_email.applied_at = applied_at
                self.session.add(existing_by_email)
                self.session.commit()
                self.session.refresh(existing_by_email)
            return existing_by_email

        summary = getattr(extraction, "summary", None)
        action_url = getattr(extraction, "action_url", None)
        event_date = getattr(extraction, "event_date", None)

        existing = self.find_application_by_company_and_role(
            extraction.company, extraction.role
        )
        if existing is not None:
            if existing.applied_at is None and applied_at is not None:
                existing.applied_at = applied_at
            return self.update_application_status(
                existing,
                extraction.status,
                notes=summary,
                action_url=action_url,
                event_date=event_date,
            )

        try:
            return self.create_application(
                company=extraction.company,
                role=extraction.role,
                status=extraction.status,
                source_email_id=email_id,
                applied_at=applied_at or utcnow(),
                sender_email=sender_email,
                notes=summary,
                action_url=action_url,
                event_date=event_date,
            )
        except IntegrityError:
            # A concurrent insert may have won the race for this email id.
            existing_by_email = self.get_application_by_email_id(email_id)
            if existing_by_email is not None:
                return existing_by_email
            raise
