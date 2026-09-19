from dataclasses import dataclass

import pytest
from sqlmodel import select

from app.db.models import Application, ApplicationStatus
from app.db.repository import ApplicationRepository


@dataclass
class FakeExtraction:
    company: str
    role: str
    status: ApplicationStatus


@pytest.fixture
def repo(session):
    return ApplicationRepository(session)


def count_applications(repo) -> int:
    return len(repo.session.exec(select(Application)).all())


def test_create_application(repo):
    application = repo.create_application(
        company="Google",
        role="Software Engineer",
        status=ApplicationStatus.UNDER_REVIEW,
        source_email_id="email_123",
    )

    assert application.id is not None
    assert application.company == "Google"
    assert application.role == "Software Engineer"
    assert application.status == ApplicationStatus.UNDER_REVIEW
    assert application.source_email_id == "email_123"
    assert application.updated_at is not None


def test_get_application_by_id(repo):
    created = repo.create_application(
        "Google", "Software Engineer", ApplicationStatus.APPLIED, "email_1"
    )

    assert repo.get_application_by_id(created.id) == created
    assert repo.get_application_by_id(9999) is None


def test_get_application_by_email_id(repo):
    created = repo.create_application(
        "Google", "Software Engineer", ApplicationStatus.APPLIED, "email_1"
    )

    assert repo.get_application_by_email_id("email_1") == created
    assert repo.get_application_by_email_id("missing") is None


def test_update_application_status(repo):
    created = repo.create_application(
        "Google", "Software Engineer", ApplicationStatus.UNDER_REVIEW, "email_1"
    )

    updated = repo.update_application_status(created, ApplicationStatus.OFFER)

    assert updated.status == ApplicationStatus.OFFER
    assert repo.get_application_by_id(created.id).status == ApplicationStatus.OFFER


def test_duplicate_source_email_id_is_prevented(repo):
    first = repo.create_application(
        "Google", "Software Engineer", ApplicationStatus.UNDER_REVIEW, "email_123"
    )

    result = repo.create_or_update_application(
        FakeExtraction("Google", "Software Engineer", ApplicationStatus.UNDER_REVIEW),
        "email_123",
    )

    assert result.id == first.id
    assert count_applications(repo) == 1


def test_direct_duplicate_email_id_raises(repo):
    repo.create_application(
        "Google", "Software Engineer", ApplicationStatus.APPLIED, "email_1"
    )

    with pytest.raises(Exception):
        repo.create_application(
            "Google", "Backend Engineer", ApplicationStatus.APPLIED, "email_1"
        )


def test_existing_application_matched_by_company_and_role(repo):
    first = repo.create_application(
        "Google", "Software Engineer", ApplicationStatus.UNDER_REVIEW, "email_1"
    )

    result = repo.create_or_update_application(
        FakeExtraction("Google", "Software Engineer", ApplicationStatus.REJECTED),
        "email_2",
    )

    assert result.id == first.id
    assert result.status == ApplicationStatus.REJECTED
    assert count_applications(repo) == 1


def test_matching_is_case_and_whitespace_insensitive(repo):
    first = repo.create_application(
        "Google", "Software Engineer", ApplicationStatus.UNDER_REVIEW, "email_1"
    )

    matched = repo.find_application_by_company_and_role(
        "  google ", "software engineer"
    )

    assert matched.id == first.id


def test_different_role_creates_new_application(repo):
    repo.create_application(
        "Google", "Software Engineer", ApplicationStatus.APPLIED, "email_1"
    )

    result = repo.create_or_update_application(
        FakeExtraction("Google", "Backend Engineer", ApplicationStatus.APPLIED),
        "email_2",
    )

    assert result.source_email_id == "email_2"
    assert count_applications(repo) == 2
