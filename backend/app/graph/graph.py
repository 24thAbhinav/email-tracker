from langsmith import traceable
from datetime import datetime
from typing import TypedDict
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from sqlmodel import Session
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv

from app.db.database import engine, create_db_and_tables
from app.db.models import ApplicationStatus
from app.db.repository import ApplicationRepository

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)
if os.getenv('LANGSMITH_API_KEY') and not os.getenv('LANGCHAIN_API_KEY'):
    os.environ['LANGCHAIN_API_KEY'] = os.environ['LANGSMITH_API_KEY']
if os.getenv('LANGSMITH_TRACING') == 'true':
    os.environ['LANGCHAIN_TRACING_V2'] = 'true'
if os.getenv('LANGSMITH_PROJECT'):
    os.environ.setdefault('LANGCHAIN_PROJECT', os.environ['LANGSMITH_PROJECT'])

OPENCODE_SESSION_ID = os.getenv("OPENCODE_SESSION_ID") or str(uuid.uuid4())


llm = ChatOpenAI(
    model="mimo-v2.5",
    api_key=os.getenv("OPENCODE_API_KEY"),
    base_url="https://opencode.ai/zen/go/v1",
    default_headers={"x-opencode-session": OPENCODE_SESSION_ID},
)


# State
class ApplicationState(TypedDict, total=False):
    email_subject: str
    email_body: str
    source_email_id: str
    sender_email: str
    received_at: datetime | None
    is_application_email: bool
    company: str
    role: str
    status: ApplicationStatus
    summary: str | None
    action_url: str | None
    event_date: str | None
    application_id: int | None


# Structured output schemas
class ApplicationExtraction(BaseModel):
    company: str
    role: str
    status: ApplicationStatus
    summary: str | None = Field(
        default=None,
        description="Concise 1-2 sentence summary of this email's status update or required action."
    )
    action_url: str | None = Field(
        default=None,
        description="Direct URL link for interview (Zoom/Meet/Teams), online assessment (HackerRank/CodeSignal/portal), or scheduling calendar if present in the email."
    )
    event_date: str | None = Field(
        default=None,
        description="Date and/or time mentioned for the interview, test deadline, or next step if specified in the email (e.g. 'Sept 25, 2026, 3:00 PM IST', 'Within 48 hours')."
    )


class Classifier(BaseModel):
    is_application_email: bool


# LLM variants
structured_llm = llm.with_structured_output(ApplicationExtraction)
classifier_llm = llm.with_structured_output(Classifier)


# Nodes
def classify_email(state: ApplicationState) -> dict:
    result = classifier_llm.invoke(
        f"""Analyze whether this email is related to a job application
(e.g. confirmation, status update, rejection, offer, OA, interview invite).

Subject: {state["email_subject"]}

Body:
{state["email_body"]}
"""
    )
    return {"is_application_email": result.is_application_email}


def extract(state: ApplicationState) -> dict:
    result = structured_llm.invoke(
        f"""You are a job application tracker.
Extract the following details from the email:
- company: Name of the company
- role: Job title / role applied for
- status: One of {[s.value for s in ApplicationStatus if s is not ApplicationStatus.CLOSED]}
  UNDER_REVIEW = application received / under review
  OA = online assessment / coding test invitation
  INTERVIEW / INTERVIEW_PASSED / INTERVIEW_REJECTED = interview stages
  OFFER = job offer extended
  REJECTED = application rejected / not selected
  Never use CLOSED; that status is set by the user only.
- summary: A concise 1-2 sentence summary describing the email update or instructions (e.g. 'Received OA link for technical round', 'Invited to 45-min technical interview').
- action_url: The primary link for the candidate if available in the text (e.g. interview link, test link, scheduling calendar link, portal login).
- event_date: Any specific scheduled date/time or deadline mentioned for the action (e.g. 'Sept 25, 2026 at 3:00 PM', 'Complete by Sept 22').

Subject: {state["email_subject"]}

Body:
{state["email_body"]}
"""
    )
    return {
        "company": result.company,
        "role": result.role,
        "status": result.status,
        "summary": result.summary,
        "action_url": result.action_url,
        "event_date": result.event_date,
    }


def make_persist_node(session_factory=lambda: Session(engine)):
    def persist(state: ApplicationState) -> dict:
        extraction = ApplicationExtraction(
            company=state["company"],
            role=state["role"],
            status=state["status"],
            summary=state.get("summary"),
            action_url=state.get("action_url"),
            event_date=state.get("event_date"),
        )
        with session_factory() as session:
            application = ApplicationRepository(session).create_or_update_application(
                extraction,
                state["source_email_id"],
                sender_email=state.get("sender_email"),
                applied_at=state.get("received_at"),
            )
            return {"application_id": application.id}

    return persist


# Conditional routing
def should_process(state: ApplicationState) -> str:
    return "process" if state["is_application_email"] else "ignore"


# Graph assembly
graph = StateGraph(ApplicationState)

graph.add_node("classify_email", classify_email)
graph.add_node("extract", extract)
graph.add_node("persist", make_persist_node())

graph.add_edge(START, "classify_email")
graph.add_conditional_edges(
    "classify_email",
    should_process,
    {
        "process": "extract",
        "ignore": END,
    },
)
graph.add_edge("extract", "persist")
graph.add_edge("persist", END)

workflow = graph.compile()


# Test invocation
if __name__ == "__main__":
    create_db_and_tables()
    result = workflow.invoke({
        "email_subject": "Application Update - Software Engineer Intern",
        "email_body": """
            Thank you for applying to Acme Corp for the Software Engineer Intern role.
            Your application is currently under review.
        """,
        "source_email_id": "test-email-1",
        "sender_email": "recruiter@acme.com",
    })
    print(result)
