import base64
import json

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db.models import Application, ApplicationStatus
from app.gmail import Email
from app.graph.graph import make_persist_node
from app.main import app, get_gmail_sync, get_workflow
from app.services.email_processor import email_to_state, process_email


def count_applications(engine) -> int:
    with Session(engine) as session:
        return len(session.exec(select(Application)).all())


def find_by_email_id(engine, email_id: str) -> Application | None:
    with Session(engine) as session:
        return session.exec(
            select(Application).where(Application.source_email_id == email_id)
        ).first()


class FakeWorkflow:
    """Stand-in for the compiled graph: stubs classify/extract, uses the real
    persist node + repository so DB behavior is exercised."""

    def __init__(
        self,
        session_factory,
        *,
        is_application_email,
        company="Acme Corp",
        role="Software Engineer",
        status=ApplicationStatus.UNDER_REVIEW,
    ):
        self._persist = make_persist_node(session_factory)
        self.is_application_email = is_application_email
        self.company = company
        self.role = role
        self.status = status

    def invoke(self, state):
        if not self.is_application_email:
            return {**state, "is_application_email": False}
        extracted = {
            **state,
            "is_application_email": True,
            "company": self.company,
            "role": self.role,
            "status": self.status,
        }
        return {**extracted, **self._persist(extracted)}


def email(email_id: str, subject="Application update", body="Under review") -> Email:
    return Email(
        id=email_id,
        thread_id=f"thread-{email_id}",
        sender="recruiter@acme.com",
        subject=subject,
        body=body,
    )


def test_email_to_state_mapping():
    state = email_to_state(email("e1", subject="Subj", body="Body"))

    assert state == {
        "email_subject": "Subj",
        "email_body": "Body",
        "source_email_id": "e1",
        "sender_email": "recruiter@acme.com",
        "received_at": None,
    }


def test_non_job_email_is_ignored(engine):
    graph = FakeWorkflow(lambda: Session(engine), is_application_email=False)

    result = process_email(email("e1", subject="Weekly newsletter"), graph=graph)

    assert result["is_application_email"] is False
    assert count_applications(engine) == 0


def test_job_email_creates_application(engine):
    graph = FakeWorkflow(lambda: Session(engine), is_application_email=True)

    result = process_email(email("e1"), graph=graph)

    assert result["application_id"] is not None
    row = find_by_email_id(engine, "e1")
    assert row is not None
    assert row.company == "Acme Corp"
    assert row.role == "Software Engineer"
    assert row.status == ApplicationStatus.UNDER_REVIEW
    assert count_applications(engine) == 1


def test_second_email_updates_existing_application(engine):
    first = process_email(
        email("e1"),
        graph=FakeWorkflow(
            lambda: Session(engine),
            is_application_email=True,
            status=ApplicationStatus.UNDER_REVIEW,
        ),
    )
    second = process_email(
        email("e2"),
        graph=FakeWorkflow(
            lambda: Session(engine),
            is_application_email=True,
            status=ApplicationStatus.REJECTED,
        ),
    )

    assert first["application_id"] == second["application_id"]
    assert count_applications(engine) == 1
    assert find_by_email_id(engine, "e1").status == ApplicationStatus.REJECTED


def test_duplicate_message_does_not_duplicate(engine):
    graph = FakeWorkflow(lambda: Session(engine), is_application_email=True)

    first = process_email(email("e1"), graph=graph)
    second = process_email(email("e1"), graph=graph)

    assert first["application_id"] == second["application_id"]
    assert count_applications(engine) == 1


# ── Webhook ─────────────────────────────────────────────────────────────────


class FakeSync:
    def __init__(self, session, emails):
        self.session = session
        self._emails = emails
        self.history_ids = []

    def process_history(self, history_id):
        self.history_ids.append(history_id)
        return list(self._emails)


def envelope(history_id: int) -> dict:
    data = base64.urlsafe_b64encode(
        json.dumps({"historyId": history_id}).encode()
    ).decode()
    return {"message": {"data": data, "messageId": "p1"}}


def test_webhook_rejects_bad_payload(engine):
    app.dependency_overrides[get_gmail_sync] = lambda: FakeSync(Session(engine), [])
    try:
        response = TestClient(app).post("/gmail/webhook", json={})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400


def test_webhook_processes_new_emails_and_skips_duplicates(engine):
    def override_sync():
        return FakeSync(Session(engine), [email("e1")])

    app.dependency_overrides[get_gmail_sync] = override_sync
    app.dependency_overrides[get_workflow] = lambda: FakeWorkflow(
        lambda: Session(engine), is_application_email=True
    )
    try:
        client = TestClient(app)

        first = client.post("/gmail/webhook", json=envelope(100))
        assert first.status_code == 200
        processed = first.json()["processed"]
        assert len(processed) == 1
        assert processed[0]["email_id"] == "e1"
        assert processed[0]["is_application_email"] is True
        assert processed[0]["application_id"] is not None

        # Same message delivered again -> skipped by source_email_id.
        second = client.post("/gmail/webhook", json=envelope(101))
        assert second.json()["processed"] == []
        assert count_applications(engine) == 1
    finally:
        app.dependency_overrides.clear()
