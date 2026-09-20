# main.py - FastAPI application entry point + Gmail webhook/auth + Static SPA

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)
if os.getenv("LANGSMITH_API_KEY") and not os.getenv("LANGCHAIN_API_KEY"):
    os.environ["LANGCHAIN_API_KEY"] = os.environ["LANGSMITH_API_KEY"]
if os.getenv("LANGSMITH_TRACING") == "true":
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
if os.getenv("LANGSMITH_PROJECT"):
    os.environ.setdefault("LANGCHAIN_PROJECT", os.environ["LANGSMITH_PROJECT"])

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.api.applications import router as applications_router
from app.db.database import create_db_and_tables, get_session
from app.db.repository import ApplicationRepository
from app.gmail import (
    GmailClient,
    GmailError,
    GmailSettings,
    GmailSync,
    authorization_url,
    decode_push,
    exchange_code,
    get_credentials,
)
from app.graph.graph import workflow
from app.services.email_processor import process_email


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="Job Tracker", lifespan=lifespan)

_origins = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in _origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_settings() -> GmailSettings:
    return GmailSettings.from_env()


def get_workflow():
    return workflow


def get_gmail_sync(
    session: Session = Depends(get_session),
    settings: GmailSettings = Depends(get_settings),
) -> GmailSync:
    client = GmailClient.from_credentials(get_credentials(settings))
    return GmailSync(
        client,
        session,
        topic=settings.topic,
        account=settings.account,
        full_sync_max=settings.full_sync_max,
    )


def _process_emails(sync: GmailSync, graph, emails) -> list[dict]:
    repo = ApplicationRepository(sync.session)
    processed: list[dict] = []
    for email in emails:
        # Same Gmail message must not be processed twice: existing source_email_id
        # is the idempotency key.
        if repo.get_application_by_email_id(email.id) is not None:
            continue
        state = process_email(email, graph=graph)
        processed.append(
            {
                "email_id": email.id,
                "is_application_email": state.get("is_application_email"),
                "application_id": state.get("application_id"),
            }
        )
    return processed


# ── Routers ─────────────────────────────────────────────────────────────────

auth_router = APIRouter(prefix="/auth", tags=["auth"])
gmail_router = APIRouter(prefix="/gmail", tags=["gmail"])


# ── One-time OAuth ──────────────────────────────────────────────────────────


@auth_router.get("/url")
def gmail_auth_url(settings: GmailSettings = Depends(get_settings)):
    """Open this in a browser to start the Google consent flow."""
    try:
        url, _state = authorization_url(settings)
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url)


@auth_router.get("/callback")
def gmail_auth_callback(
    code: str | None = None,
    settings: GmailSettings = Depends(get_settings),
):
    """Google redirects here; exchanges the code and stores token.json."""
    if not code:
        raise HTTPException(status_code=400, detail="Missing ?code from Google")
    try:
        exchange_code(settings, code)
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "authorized", "token_path": settings.token_path}


# ── Gmail watch + ingestion ─────────────────────────────────────────────────


@gmail_router.post("/watch")
def gmail_watch(sync: GmailSync = Depends(get_gmail_sync)) -> dict:
    """Start/renew the Gmail push watch."""
    try:
        return sync.start_watch()
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@gmail_router.post("/sync")
def gmail_manual_sync(
    sync: GmailSync = Depends(get_gmail_sync),
    graph=Depends(get_workflow),
) -> dict:
    """Manually pull recent messages (useful for local testing without Pub/Sub)."""
    emails = sync.full_sync()
    return {"fetched": len(emails), "processed": _process_emails(sync, graph, emails)}


@gmail_router.post("/webhook")
def gmail_webhook(
    envelope: dict,
    sync: GmailSync = Depends(get_gmail_sync),
    graph=Depends(get_workflow),
) -> dict:
    """Receive a Pub/Sub push, sync Gmail history, process each new email."""
    try:
        notification = decode_push(envelope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    emails = sync.process_history(notification["history_id"])
    return {"processed": _process_emails(sync, graph, emails)}


# Register API routes (both direct and with /api prefix for frontend/backend flexibility)
app.include_router(applications_router)
app.include_router(applications_router, prefix="/api")
app.include_router(auth_router)
app.include_router(auth_router, prefix="/api")
app.include_router(gmail_router)
app.include_router(gmail_router, prefix="/api")


# ── Static React SPA Serving ───────────────────────────────────────────────

_frontend_dist = Path("/app/frontend/dist")
if not _frontend_dist.exists():
    _frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if _frontend_dist.exists():
    _assets = _frontend_dist / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't serve index.html for API paths that 404
        if full_path.startswith(("api/", "auth/", "gmail/", "applications/")):
            raise HTTPException(status_code=404, detail="Not Found")
        file_path = _frontend_dist / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dist / "index.html")
