import base64
import json

import pytest
from googleapiclient.errors import HttpError

from app.gmail import (
    Email,
    GmailClient,
    GmailHistoryExpired,
    GmailSync,
    GmailSyncState,  # noqa: F401  (registers the table for the engine fixture)
    decode_push,
    handle_push,
    parse_message,
)


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


# ── Parsing ─────────────────────────────────────────────────────────────────


def raw_message(payload, **extra):
    message = {
        "id": "m1",
        "threadId": "t1",
        "internalDate": "1700000000000",
        "snippet": "snippet fallback",
        "labelIds": ["INBOX"],
        "payload": payload,
    }
    message.update(extra)
    return message


def test_parse_plain_text_email():
    email = parse_message(
        raw_message(
            {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": "recruiter@acme.com"},
                    {"name": "Subject", "value": "Application Update"},
                ],
                "body": {"data": b64("Your application is under review.")},
            }
        )
    )

    assert (email.id, email.thread_id) == ("m1", "t1")
    assert email.sender == "recruiter@acme.com"
    assert email.subject == "Application Update"
    assert email.body == "Your application is under review."
    assert email.received_at is not None and email.received_at.tzinfo is not None


def test_parse_multipart_prefers_plain_text():
    email = parse_message(
        raw_message(
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": b64("plain body")}},
                    {"mimeType": "text/html", "body": {"data": b64("<p>html</p>")}},
                ],
            }
        )
    )

    assert email.body == "plain body"


def test_parse_html_only_is_converted():
    email = parse_message(
        raw_message(
            {
                "mimeType": "text/html",
                "body": {"data": b64("<div>Hello <b>world</b><br>line two</div>")},
            }
        )
    )

    assert "<" not in email.body
    assert "Hello" in email.body and "world" in email.body and "line two" in email.body


def test_parse_nested_multipart():
    email = parse_message(
        raw_message(
            {
                "mimeType": "multipart/mixed",
                "parts": [
                    {
                        "mimeType": "multipart/alternative",
                        "parts": [
                            {"mimeType": "text/plain", "body": {"data": b64("nested")}}
                        ],
                    },
                    {"mimeType": "application/pdf", "body": {"attachmentId": "x"}},
                ],
            }
        )
    )

    assert email.body == "nested"


def test_parse_falls_back_to_snippet():
    email = parse_message(raw_message({"mimeType": "multipart/mixed", "parts": []}))

    assert email.body == "snippet fallback"


# ── GmailClient (mocked google service) ─────────────────────────────────────


class FakeRequest:
    def __init__(self, result=None, error=None):
        self._result, self._error = result, error

    def execute(self):
        if self._error is not None:
            raise self._error
        return self._result


class FakeMessages:
    def __init__(self, service):
        self._s = service

    def get(self, **kw):
        self._s.calls.append(("messages.get", kw))
        return FakeRequest(self._s.message)

    def list(self, **kw):
        self._s.calls.append(("messages.list", kw))
        return FakeRequest(self._s.message_list)


class FakeHistory:
    def __init__(self, service):
        self._s = service

    def list(self, **kw):
        self._s.calls.append(("history.list", kw))
        return FakeRequest(
            getattr(self._s, "history", None), getattr(self._s, "history_error", None)
        )


class FakeUsers:
    def __init__(self, service):
        self._s = service

    def getProfile(self, **kw):
        return FakeRequest(self._s.profile)

    def watch(self, **kw):
        self._s.calls.append(("watch", kw))
        return FakeRequest(self._s.watch_result)

    def stop(self, **kw):
        self._s.calls.append(("stop", kw))
        return FakeRequest({})

    def messages(self):
        return FakeMessages(self._s)

    def history(self):
        return FakeHistory(self._s)


class FakeService:
    def __init__(self, **data):
        self.__dict__.update(data)
        self.calls = []

    def users(self):
        return FakeUsers(self)


def http_404():
    class Resp:
        status, reason = 404, "Not Found"

    return HttpError(Resp(), b"nope")


def test_client_get_message_and_history_id():
    message = raw_message(
        {
            "mimeType": "text/plain",
            "headers": [{"name": "Subject", "value": "Hi"}],
            "body": {"data": b64("body")},
        }
    )
    client = GmailClient(FakeService(message=message, profile={"historyId": 999}))

    email = client.get_message("m1")

    assert email.subject == "Hi" and email.body == "body"
    assert client.get_history_id() == "999"


def test_client_watch_returns_state():
    service = FakeService(watch_result={"historyId": 123, "expiration": "1700000000000"})
    result = GmailClient(service).start_watch("projects/p/topics/t")

    assert result["history_id"] == "123"
    assert result["expiration"] is not None
    assert service.calls[0][1]["body"]["topicName"] == "projects/p/topics/t"


def test_client_history_collects_ids_and_expiry():
    service = FakeService(
        history={
            "historyId": "555",
            "nextPageToken": "p2",
            "history": [
                {"messages": [{"id": "m1"}], "messagesAdded": [{"message": {"id": "m2"}}]}
            ],
        }
    )
    page = GmailClient(service).get_history("100")

    assert set(page["message_ids"]) == {"m1", "m2"}
    assert page["history_id"] == "555"
    assert page["next_page_token"] == "p2"


def test_client_history_expired_raises():
    with pytest.raises(GmailHistoryExpired):
        GmailClient(FakeService(history_error=http_404())).get_history("100")


# ── GmailSync (fake client + in-memory DB) ──────────────────────────────────


class FakeGmailClient:
    def __init__(self, pages=None, messages=None, profile_history_id=None, listed=None):
        self.pages = pages or {}
        self.messages = messages or {}
        self.profile_history_id = profile_history_id
        self.listed = listed or []
        self.expired = False
        self.history_calls = []

    def get_history(self, start, *, page_token=None):
        self.history_calls.append((start, page_token))
        if self.expired:
            raise GmailHistoryExpired("expired")
        return self.pages.get(page_token, {"message_ids": [], "history_id": None,
                                           "next_page_token": None})

    def get_message(self, message_id):
        return self.messages.get(
            message_id,
            Email(id=message_id, thread_id=message_id, sender="s@x.com",
                  subject="S", body="B"),
        )

    def get_history_id(self):
        return self.profile_history_id

    def list_message_ids(self, *, max_results=50):
        return self.listed

    def start_watch(self, topic, *, label_ids=()):
        return {"history_id": "42", "expiration": None}


def sync(session, client):
    return GmailSync(client, session, topic="projects/p/topics/t")


def test_sync_paginates_and_dedupes(session):
    client = FakeGmailClient(
        pages={
            None: {"message_ids": ["m1"], "history_id": "150", "next_page_token": "p2"},
            "p2": {"message_ids": ["m1", "m2"], "history_id": "160",
                   "next_page_token": None},
        }
    )
    emails = sync(session, client).process_history("150")

    assert [e.id for e in emails] == ["m1", "m2"]
    assert client.history_calls == [("150", None), ("150", "p2")]


def test_sync_persists_cursor(session):
    client = FakeGmailClient(
        pages={None: {"message_ids": [], "history_id": "160", "next_page_token": None}}
    )
    service = sync(session, client)
    service.process_history("150")

    assert service._state().history_id == "160"


def test_sync_duplicate_and_older_history_id_are_noops(session):
    client = FakeGmailClient(
        pages={None: {"message_ids": ["m1"], "history_id": "160",
                      "next_page_token": None}}
    )
    service = sync(session, client)
    service.process_history("160")

    assert service.process_history("160") == []
    assert service.process_history("150") == []
    assert len(client.history_calls) == 1
    assert service._state().history_id == "160"


def test_sync_expired_history_triggers_full_sync(session):
    client = FakeGmailClient(profile_history_id="999", listed=["m9"])
    client.expired = True
    service = sync(session, client)

    emails = service.process_history("100")

    assert [e.id for e in emails] == ["m9"]
    assert service._state().history_id == "999"


def test_sync_start_watch_persists_state(session):
    service = sync(session, FakeGmailClient())

    service.start_watch()

    assert service._state().history_id == "42"
    assert service.watch_needs_renewal() is True  # no expiration stored


# ── Pub/Sub ─────────────────────────────────────────────────────────────────


def envelope(payload):
    return {
        "message": {"data": b64(json.dumps(payload)), "messageId": "p1"},
        "subscription": "projects/p/subscriptions/s",
    }


def test_decode_push():
    decoded = decode_push(envelope({"emailAddress": "me@x.com", "historyId": 12345}))

    assert decoded["history_id"] == "12345"
    assert decoded["email_address"] == "me@x.com"


def test_decode_push_rejects_bad_input():
    with pytest.raises(ValueError):
        decode_push({"subscription": "x"})
    with pytest.raises(ValueError):
        decode_push({"message": {"data": "!!!not-base64!!!"}})
    with pytest.raises(ValueError):
        decode_push(envelope({"emailAddress": "me@x.com"}))


def test_handle_push_calls_sync(session):
    client = FakeGmailClient(
        pages={None: {"message_ids": ["m1"], "history_id": "160",
                      "next_page_token": None}}
    )
    emails = handle_push(envelope({"historyId": 150}), sync(session, client))

    assert [e.id for e in emails] == ["m1"]
