from sqlmodel import Session, select

from app.db.models import Application, ApplicationStatus
from app.graph.graph import make_persist_node


def make_state(**overrides):
    state = {
        "company": "Acme Corp",
        "role": "Software Engineer Intern",
        "status": ApplicationStatus.UNDER_REVIEW,
        "source_email_id": "email_1",
    }
    state.update(overrides)
    return state


def count_applications(engine) -> int:
    with Session(engine) as session:
        return len(session.exec(select(Application)).all())


def get_application(engine, application_id: int) -> Application:
    with Session(engine) as session:
        return session.get(Application, application_id)


def test_persist_creates_application(engine):
    node = make_persist_node(lambda: Session(engine))

    result = node(make_state())

    assert result["application_id"] is not None
    assert count_applications(engine) == 1


def test_persist_is_idempotent_for_same_email(engine):
    node = make_persist_node(lambda: Session(engine))

    first = node(make_state())
    second = node(make_state())

    assert first["application_id"] == second["application_id"]
    assert count_applications(engine) == 1


def test_persist_updates_status_for_same_company_and_role(engine):
    node = make_persist_node(lambda: Session(engine))

    first = node(make_state(source_email_id="email_1"))
    second = node(
        make_state(source_email_id="email_2", status=ApplicationStatus.REJECTED)
    )

    assert first["application_id"] == second["application_id"]
    assert count_applications(engine) == 1
    assert get_application(engine, first["application_id"]).status == (
        ApplicationStatus.REJECTED
    )
