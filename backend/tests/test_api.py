import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db.database import get_session
from app.db.models import ApplicationStatus
from app.db.repository import ApplicationRepository
from app.main import app


@pytest.fixture
def client(engine):
    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def seed(engine, company, role, status=ApplicationStatus.APPLIED, email_id=None):
    with Session(engine) as session:
        application = ApplicationRepository(session).create_application(
            company=company,
            role=role,
            status=status,
            source_email_id=email_id or f"{company}-{role}-email",
        )
        return application.id


def test_list_applications(client, engine):
    seed(engine, "Google", "SWE Intern", ApplicationStatus.UNDER_REVIEW)
    seed(engine, "Amazon", "SDE Intern", ApplicationStatus.REJECTED)

    response = client.get("/applications")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert {"id", "company", "role", "status", "updated_at"} <= body["items"][0].keys()


def test_list_filter_by_status(client, engine):
    seed(engine, "Google", "SWE Intern", ApplicationStatus.UNDER_REVIEW)
    seed(engine, "Amazon", "SDE Intern", ApplicationStatus.OFFER)

    response = client.get("/applications", params={"status": "OFFER"})

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["company"] == "Amazon"


def test_list_search_matches_company_or_role(client, engine):
    seed(engine, "Google", "SWE Intern")
    seed(engine, "Amazon", "SDE Intern")

    response = client.get("/applications", params={"search": "goog"})

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["company"] == "Google"


def test_list_pagination(client, engine):
    for index in range(3):
        seed(engine, f"Company {index}", "Role")

    response = client.get("/applications", params={"limit": 2, "offset": 0})

    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["limit"] == 2


def test_get_application(client, engine):
    application_id = seed(engine, "Acme Corp", "Backend Intern")

    response = client.get(f"/applications/{application_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == application_id
    assert body["company"] == "Acme Corp"
    assert body["role"] == "Backend Intern"
    assert body["status"] == "APPLIED"


def test_get_application_not_found(client):
    response = client.get("/applications/99999")

    assert response.status_code == 404


def test_get_application_events(client, engine):
    application_id = seed(
        engine, "Acme Corp", "Backend Intern", ApplicationStatus.UNDER_REVIEW
    )
    with Session(engine) as session:
        repo = ApplicationRepository(session)
        application = repo.get_application_by_id(application_id)
        repo.update_application_status(application, ApplicationStatus.INTERVIEW)

    response = client.get(f"/applications/{application_id}/events")

    assert response.status_code == 200
    events = response.json()
    assert [event["status"] for event in events] == ["UNDER_REVIEW", "INTERVIEW"]
    assert all(event["application_id"] == application_id for event in events)


def test_get_application_events_not_found(client):
    response = client.get("/applications/99999/events")

    assert response.status_code == 404


def test_close_sets_status_closed_and_reopen_restores(client, engine):
    application_id = seed(
        engine, "Acme Corp", "Backend Intern", ApplicationStatus.UNDER_REVIEW
    )

    closed = client.patch(f"/applications/{application_id}", json={"is_closed": True})

    assert closed.status_code == 200
    body = closed.json()
    assert body["is_closed"] is True
    assert body["status"] == "CLOSED"
    assert body["closed_at"] is not None

    reopened = client.patch(
        f"/applications/{application_id}", json={"is_closed": False}
    )

    assert reopened.status_code == 200
    assert reopened.json()["is_closed"] is False
    assert reopened.json()["status"] == "UNDER_REVIEW"
    assert reopened.json()["closed_at"] is None


def test_list_filter_by_closed_status(client, engine):
    open_id = seed(engine, "Google", "SWE Intern", ApplicationStatus.UNDER_REVIEW)
    closed_id = seed(engine, "Amazon", "SDE Intern", ApplicationStatus.APPLIED)
    client.patch(f"/applications/{closed_id}", json={"is_closed": True})

    response = client.get("/applications", params={"status": "CLOSED"})

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == closed_id
    assert body["items"][0]["id"] != open_id


def test_stats_and_include_closed(client, engine):
    seed(engine, "Google", "SWE Intern", ApplicationStatus.UNDER_REVIEW)
    seed(engine, "Amazon", "SDE Intern", ApplicationStatus.OFFER)
    closed_id = seed(engine, "Meta", "PE", ApplicationStatus.APPLIED)
    client.patch(f"/applications/{closed_id}", json={"is_closed": True})

    stats = client.get("/applications/stats").json()

    assert stats["total"] == 2
    assert stats["closed"] == 1
    assert stats["by_status"]["CLOSED"] == 1
    assert stats["by_status"]["OFFER"] == 1
    assert stats["by_status"]["APPLIED"] == 0

    assert client.get("/applications").json()["total"] == 3
    visible = client.get("/applications", params={"include_closed": False}).json()
    assert visible["total"] == 2


def test_close_application_not_found(client):
    response = client.patch("/applications/99999", json={"is_closed": True})

    assert response.status_code == 404
