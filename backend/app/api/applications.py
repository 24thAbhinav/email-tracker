# applications.py - read-only dashboard endpoints

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.api.schemas import (
    ApplicationEventRead,
    ApplicationListResponse,
    ApplicationRead,
)
from app.db.database import get_session
from app.db.models import ApplicationStatus
from app.db.repository import ApplicationRepository

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=ApplicationListResponse)
def list_applications(
    status: ApplicationStatus | None = None,
    company: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> ApplicationListResponse:
    items, total = ApplicationRepository(session).list_applications(
        status=status,
        company=company,
        search=search,
        limit=limit,
        offset=offset,
    )
    return ApplicationListResponse(
        items=[
            ApplicationRead.model_validate(item, from_attributes=True)
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{application_id}", response_model=ApplicationRead)
def get_application(
    application_id: int,
    session: Session = Depends(get_session),
) -> ApplicationRead:
    application = ApplicationRepository(session).get_application_by_id(application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return ApplicationRead.model_validate(application, from_attributes=True)


@router.get("/{application_id}/events", response_model=list[ApplicationEventRead])
def get_application_events(
    application_id: int,
    session: Session = Depends(get_session),
) -> list[ApplicationEventRead]:
    repo = ApplicationRepository(session)
    if repo.get_application_by_id(application_id) is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return [
        ApplicationEventRead.model_validate(event, from_attributes=True)
        for event in repo.list_events(application_id)
    ]
