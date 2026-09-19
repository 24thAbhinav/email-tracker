from typing import TypedDict
from enum import StrEnum
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

OPENCODE_SESSION_ID = os.getenv("OPENCODE_SESSION_ID") or str(uuid.uuid4())



class ApplicationStatus(StrEnum):
    APPLIED = "APPLIED"
    UNDER_REVIEW = "UNDER_REVIEW"
    OA = "OA"
    INTERVIEW = "INTERVIEW"
    INTERVIEW_PASSED = "INTERVIEW_PASSED"
    INTERVIEW_REJECTED = "INTERVIEW_REJECTED"
    OFFER = "OFFER"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


llm = ChatOpenAI(
    model="mimo-v2.5",
    api_key=os.getenv("OPENCODE_API_KEY"),
    base_url="https://opencode.ai/zen/go/v1",
    default_headers={"x-opencode-session": OPENCODE_SESSION_ID},
)


# State
class ApplicationState(TypedDict):
    email_subject: str
    email_body: str
    is_application_email: bool
    company: str
    position: str
    status: ApplicationStatus


# Structured output schemas
class ApplicationOutput(BaseModel):
    company: str
    status: ApplicationStatus
    position: str


class Classifier(BaseModel):
    is_application_email: bool


# LLM variants
structured_llm = llm.with_structured_output(ApplicationOutput)
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
Extract the following from the email and respond in the required format:
- company: name of the company
- position: job title / role applied for
- status: one of {[s.value for s in ApplicationStatus]}
  UNDER_REVIEW = application being reviewed
  OA = online assessment
  INTERVIEW / INTERVIEW_PASSED / INTERVIEW_REJECTED = interview stages

Subject: {state["email_subject"]}

Body:
{state["email_body"]}
"""
    )
    return {
        "company": result.company,
        "position": result.position,
        "status": result.status,
    }


# Conditional routing
def should_process(state: ApplicationState) -> str:
    return "process" if state["is_application_email"] else "ignore"


# Graph assembly
graph = StateGraph(ApplicationState)

graph.add_node("classify_email", classify_email)
graph.add_node("extract", extract)

graph.add_edge(START, "classify_email")
graph.add_conditional_edges(
    "classify_email",
    should_process,
    {
        "process": "extract",
        "ignore": END,
    },
)
graph.add_edge("extract", END)

workflow = graph.compile()


# Test invocation
if __name__ == "__main__":
    result = workflow.invoke({
        "email_subject": "Application Update - Software Engineer Intern",
        "email_body": """
            Thank you for applying to Acme Corp for the Software Engineer Intern role.
            Your application is currently under review.
        """,
    })
    print(result)
