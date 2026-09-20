# email_processor.py - boundary between Gmail ingestion and the LangGraph workflow.
#
# Translates a normalized Gmail Email into the existing ApplicationState and
# invokes the compiled graph. Contains no Gmail API knowledge.

from __future__ import annotations

from langsmith import traceable

from app.gmail import Email
from app.graph.graph import ApplicationState, workflow


def email_to_state(email: Email) -> ApplicationState:
    """Map a normalized Email onto the graph's input state."""
    return {
        "email_subject": email.subject,
        "email_body": email.body,
        "source_email_id": email.id,
        "sender_email": email.sender,
        "received_at": email.received_at,
    }


def process_email(email: Email, *, graph=workflow) -> dict:
    """Run one normalized Email through the application-tracking graph."""
    run_name = f"Email: {email.subject[:50]}" if email.subject else f"Email: {email.id}"
    config = {
        "run_name": run_name,
        "tags": ["email-processor", "job-tracker"],
        "metadata": {
            "email_id": email.id,
            "sender": email.sender,
            "subject": email.subject,
        },
    }
    return graph.invoke(email_to_state(email), config=config)
