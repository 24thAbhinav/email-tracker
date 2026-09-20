# client.py - Gmail integration: OAuth, watch, history sync, Pub/Sub, parsing.
# Everything Gmail lives here on purpose.

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel
from sqlalchemy import DateTime
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, select

from app.db.models import utcnow

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Narrowest scope that can read messages + history.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
USER_ID = "me"

# PKCE: store the code_verifier between /auth/url and /auth/callback.
# Safe for a single-user personal app.
_pending_code_verifier: str | None = None


class GmailError(RuntimeError):
    """Anything Gmail-related that the caller should handle."""


class GmailHistoryExpired(GmailError):
    """Gmail no longer has history for our cursor; call full_sync()."""


# ── Settings ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GmailSettings:
    client_id: str | None
    client_secret: str | None
    redirect_uri: str | None
    token_path: str
    credentials_path: str | None
    topic: str | None
    account: str
    full_sync_max: int

    @classmethod
    def from_env(cls) -> "GmailSettings":
        root = Path(__file__).resolve().parents[2]

        def path(env: str, default: str | None = None) -> str | None:
            value = os.getenv(env) or default
            if not value:
                return None
            p = Path(value)
            return str(p if p.is_absolute() else root / p)

        try:
            full_sync_max = int(os.getenv("GMAIL_FULL_SYNC_MAX_MESSAGES", "50"))
        except ValueError:
            full_sync_max = 50

        return cls(
            client_id=os.getenv("GOOGLE_CLIENT_ID") or None,
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET") or None,
            redirect_uri=os.getenv("GOOGLE_REDIRECT_URI") or None,
            token_path=path("GMAIL_TOKEN_PATH", "token.json") or "",
            credentials_path=path("GMAIL_CREDENTIALS_PATH", "credentials.json"),
            topic=os.getenv("GMAIL_PUBSUB_TOPIC") or None,
            account=os.getenv("GMAIL_SYNC_ACCOUNT") or USER_ID,
            full_sync_max=full_sync_max,
        )

    def require_topic(self) -> str:
        if not self.topic:
            raise GmailError(
                "GMAIL_PUBSUB_TOPIC is required, e.g. "
                "projects/<project-id>/topics/<topic-name>"
            )
        return self.topic


# ── OAuth ───────────────────────────────────────────────────────────────────


def _build_flow(settings: GmailSettings) -> Flow:
    if settings.credentials_path and Path(settings.credentials_path).exists():
        return Flow.from_client_secrets_file(
            settings.credentials_path, scopes=SCOPES, redirect_uri=settings.redirect_uri
        )
    if not (settings.client_id and settings.client_secret):
        raise GmailError(
            "Set GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET or provide GMAIL_CREDENTIALS_PATH."
        )
    if not settings.redirect_uri:
        raise GmailError("GOOGLE_REDIRECT_URI is required.")
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.client_id,
                "client_secret": settings.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.redirect_uri],
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.redirect_uri,
    )


def authorization_url(settings: GmailSettings, *, state: str | None = None):
    """Return (url, state) to send the user to for consent."""
    global _pending_code_verifier
    flow = _build_flow(settings)
    url, returned_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    # Capture PKCE code_verifier so the callback can reuse it.
    _pending_code_verifier = getattr(flow, "code_verifier", None)
    return url, returned_state


def save_credentials(settings: GmailSettings, credentials: Credentials) -> None:
    path = Path(settings.token_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(credentials.to_json())
    os.chmod(path, 0o600)


def exchange_code(settings: GmailSettings, code: str) -> Credentials:
    """Exchange the OAuth callback code, save the token, return credentials."""
    global _pending_code_verifier
    flow = _build_flow(settings)
    # Reattach the PKCE verifier generated during authorization_url().
    if _pending_code_verifier:
        flow.code_verifier = _pending_code_verifier
        _pending_code_verifier = None
    flow.fetch_token(code=code)
    credentials = flow.credentials
    save_credentials(settings, credentials)
    return credentials


def get_credentials(settings: GmailSettings) -> Credentials:
    """Load the saved token, refreshing it if needed."""
    path = Path(settings.token_path)
    if not path.exists():
        raise GmailError("No Gmail token. Complete the OAuth flow first.")
    try:
        credentials = Credentials.from_authorized_user_info(
            json.loads(path.read_text()), scopes=SCOPES
        )
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        raise GmailError(f"Could not read token at {path}.") from exc
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        save_credentials(settings, credentials)
    if not credentials.valid:
        raise GmailError("Stored Gmail credentials are invalid. Re-run OAuth.")
    return credentials


# ── Email + parsing ─────────────────────────────────────────────────────────


class Email(BaseModel):
    id: str
    thread_id: str
    sender: str
    subject: str
    body: str
    received_at: datetime | None = None
    snippet: str | None = None
    label_ids: list[str] = []


def _decode(data: str) -> str:
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding).decode("utf-8", errors="replace")


def _headers(payload: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for header in payload.get("headers") or []:
        name = (header.get("name") or "").lower()
        if name and name not in out:
            out[name] = header.get("value", "")
    return out


class _HtmlText(HTMLParser):
    _BLOCKS = {
        "address", "article", "aside", "blockquote", "br", "div", "footer",
        "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "ol", "p",
        "pre", "section", "table", "tr", "ul",
    }
    _SKIP = {"script", "style", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCKS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag in self._BLOCKS:
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def text(self) -> str:
        lines = [line.strip() for line in "".join(self._parts).splitlines()]
        return "\n".join(line for line in lines if line)


def _html_to_text(html: str) -> str:
    parser = _HtmlText()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return html
    return parser.text()


def _iter_parts(payload: dict):
    yield payload
    for part in payload.get("parts") or []:
        yield from _iter_parts(part)


def _body(payload: dict) -> str:
    plain: list[str] = []
    html: list[str] = []
    for part in _iter_parts(payload):
        data = (part.get("body") or {}).get("data")
        if not data:
            continue
        if part.get("mimeType") == "text/plain":
            plain.append(_decode(data))
        elif part.get("mimeType") == "text/html":
            html.append(_decode(data))
    if any(text.strip() for text in plain):
        return "\n".join(text for text in plain if text.strip()).strip()
    if any(text.strip() for text in html):
        return _html_to_text("\n".join(html)).strip()

    data = (payload.get("body") or {}).get("data")
    if data:
        text = _decode(data)
        if payload.get("mimeType") == "text/html":
            return _html_to_text(text).strip()
        return text.strip()
    return ""


def _received_at(value: Any) -> datetime | None:
    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)


def parse_message(raw: dict) -> Email:
    """Turn a Gmail messages.get response into a normalized Email."""
    payload = raw.get("payload") or {}
    headers = _headers(payload)
    return Email(
        id=raw.get("id", ""),
        thread_id=raw.get("threadId", ""),
        sender=headers.get("from", ""),
        subject=headers.get("subject", ""),
        body=_body(payload) or (raw.get("snippet") or "").strip(),
        received_at=_received_at(raw.get("internalDate")),
        snippet=raw.get("snippet"),
        label_ids=list(raw.get("labelIds") or []),
    )


# ── Gmail API client ────────────────────────────────────────────────────────


def _expiration(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


class GmailClient:
    def __init__(self, service: Any, *, user_id: str = USER_ID) -> None:
        self._service = service
        self._user_id = user_id

    @classmethod
    def from_credentials(cls, credentials: Credentials, *, user_id: str = USER_ID):
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        return cls(service, user_id=user_id)

    def get_profile(self) -> dict:
        return self._service.users().getProfile(userId=self._user_id).execute()

    def get_history_id(self) -> str | None:
        history_id = self.get_profile().get("historyId")
        return str(history_id) if history_id is not None else None

    def start_watch(self, topic: str, *, label_ids: tuple[str, ...] = ("INBOX",)):
        body: dict[str, Any] = {"topicName": topic}
        if label_ids:
            body["labelIds"] = list(label_ids)
        response = self._service.users().watch(userId=self._user_id, body=body).execute()
        history_id = response.get("historyId")
        return {
            "history_id": str(history_id) if history_id is not None else None,
            "expiration": _expiration(response.get("expiration")),
        }

    def renew_watch(self, topic: str, *, label_ids: tuple[str, ...] = ("INBOX",)):
        return self.start_watch(topic, label_ids=label_ids)

    def stop_watch(self) -> None:
        self._service.users().stop(userId=self._user_id).execute()

    def get_history(self, start_history_id: str, *, page_token: str | None = None):
        """One page of history changes. Raises GmailHistoryExpired on 404."""
        try:
            response = (
                self._service.users()
                .history()
                .list(
                    userId=self._user_id,
                    startHistoryId=str(start_history_id),
                    pageToken=page_token,
                    historyTypes=["messageAdded"],
                )
                .execute()
            )
        except HttpError as exc:
            if getattr(getattr(exc, "resp", None), "status", None) == 404:
                raise GmailHistoryExpired(
                    f"History for startHistoryId={start_history_id} expired."
                ) from exc
            raise

        ids: list[str] = []
        for record in response.get("history") or []:
            for message in record.get("messages") or []:
                if message.get("id"):
                    ids.append(message["id"])
            for added in record.get("messagesAdded") or []:
                message = added.get("message") or {}
                if message.get("id"):
                    ids.append(message["id"])

        history_id = response.get("historyId")
        return {
            "message_ids": ids,
            "history_id": str(history_id) if history_id is not None else None,
            "next_page_token": response.get("nextPageToken"),
        }

    def get_message(self, message_id: str) -> Email:
        raw = (
            self._service.users()
            .messages()
            .get(userId=self._user_id, id=message_id, format="full")
            .execute()
        )
        return parse_message(raw)

    def list_message_ids(self, *, max_results: int = 50) -> list[str]:
        response = (
            self._service.users()
            .messages()
            .list(userId=self._user_id, maxResults=max_results)
            .execute()
        )
        return [message["id"] for message in response.get("messages") or []]


# ── Sync cursor (integration metadata, not application data) ────────────────


class GmailSyncState(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account: str = Field(unique=True, index=True)
    history_id: str | None = None
    watch_expiration: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"onupdate": utcnow},
    )


def create_sync_table() -> None:
    from app.db.database import engine

    GmailSyncState.metadata.create_all(engine)


# ── Sync orchestration ──────────────────────────────────────────────────────


def _newer(incoming: str, stored: str | None) -> bool:
    if not stored:
        return True
    try:
        return int(incoming) > int(stored)
    except (TypeError, ValueError):
        return incoming != stored


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


class GmailSync:
    """Turns Gmail push notifications into normalized emails.

    Holds no LLM / LangGraph / application-persistence logic.
    """

    def __init__(
        self,
        client: GmailClient,
        session: Session,
        *,
        topic: str | None = None,
        account: str = USER_ID,
        full_sync_max: int = 50,
    ) -> None:
        self.client = client
        self.session = session
        self.topic = topic
        self.account = account
        self.full_sync_max = full_sync_max

    def _state(self) -> GmailSyncState:
        state = self.session.exec(
            select(GmailSyncState).where(GmailSyncState.account == self.account)
        ).first()
        if state is None:
            state = GmailSyncState(account=self.account)
            self.session.add(state)
            try:
                self.session.commit()
            except IntegrityError:
                self.session.rollback()
                state = self.session.exec(
                    select(GmailSyncState).where(
                        GmailSyncState.account == self.account
                    )
                ).first()
                if state is None:
                    raise
            self.session.refresh(state)
        return state

    def _save(self, history_id: str | None = None, expiration=None) -> None:
        state = self._state()
        if history_id is not None:
            state.history_id = history_id
        if expiration is not None:
            state.watch_expiration = expiration
        state.updated_at = utcnow()
        self.session.add(state)
        self.session.commit()
        self.session.refresh(state)

    def start_watch(self, *, label_ids: tuple[str, ...] = ("INBOX",)):
        if not self.topic:
            raise GmailError("A Pub/Sub topic is required to start a watch.")
        result = self.client.start_watch(self.topic, label_ids=label_ids)
        self._save(result["history_id"], result["expiration"])
        return result

    def renew_watch(self, *, label_ids: tuple[str, ...] = ("INBOX",)):
        return self.start_watch(label_ids=label_ids)

    def watch_needs_renewal(self, *, skew: timedelta = timedelta(hours=1)) -> bool:
        expiration = self._state().watch_expiration
        if expiration is None:
            return True
        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=timezone.utc)
        return expiration - skew <= datetime.now(timezone.utc)

    def process_history(self, history_id: str) -> list[Email]:
        """Idempotent: duplicate/older historyIds are a no-op."""
        state = self._state()
        if state.history_id and not _newer(history_id, state.history_id):
            return []

        try:
            message_ids, latest = self._collect(state.history_id or history_id)
        except GmailHistoryExpired:
            return self.full_sync()

        emails = self._fetch(message_ids)
        self._save(latest or history_id)
        return emails

    def full_sync(self, *, max_messages: int | None = None) -> list[Email]:
        """Re-establish the cursor after Gmail history expires."""
        history_id = self.client.get_history_id()
        emails = self._fetch(
            self.client.list_message_ids(max_results=max_messages or self.full_sync_max)
        )
        if history_id is not None:
            self._save(history_id)
        return emails

    def _collect(self, start_history_id: str) -> tuple[list[str], str | None]:
        message_ids: list[str] = []
        latest: str | None = None
        page_token: str | None = None
        while True:
            page = self.client.get_history(start_history_id, page_token=page_token)
            message_ids.extend(page["message_ids"])
            latest = page["history_id"] or latest
            page_token = page["next_page_token"]
            if not page_token:
                break
        return _unique(message_ids), latest

    def _fetch(self, message_ids: list[str]) -> list[Email]:
        emails: list[Email] = []
        for message_id in _unique(message_ids):
            try:
                emails.append(self.client.get_message(message_id))
            except HttpError as exc:
                if getattr(getattr(exc, "resp", None), "status", None) == 404:
                    continue
                raise
        return emails


# ── Pub/Sub push ────────────────────────────────────────────────────────────


def decode_push(envelope: dict) -> dict:
    """Decode a Pub/Sub push body into its Gmail notification fields."""
    message = envelope.get("message") if isinstance(envelope, dict) else None
    if not isinstance(message, dict) or "data" not in message:
        raise ValueError("Invalid Pub/Sub envelope: missing message.data")
    encoded = message["data"]
    try:
        decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        payload = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid Pub/Sub message data") from exc
    if not isinstance(payload, dict) or payload.get("historyId") is None:
        raise ValueError("Gmail notification is missing historyId")
    return {
        "history_id": str(payload["historyId"]),
        "email_address": payload.get("emailAddress"),
        "message_id": message.get("messageId"),
    }


def handle_push(envelope: dict, sync: GmailSync) -> list[Email]:
    """Decode a push and process it. No LLM / LangGraph / app writes here."""
    return sync.process_history(decode_push(envelope)["history_id"])
