# Gmail integration. All of it lives in client.py.

from app.gmail.client import (
    SCOPES,
    Email,
    GmailClient,
    GmailError,
    GmailHistoryExpired,
    GmailSettings,
    GmailSync,
    GmailSyncState,
    authorization_url,
    create_sync_table,
    decode_push,
    exchange_code,
    get_credentials,
    handle_push,
    parse_message,
    save_credentials,
)

__all__ = [
    "SCOPES",
    "Email",
    "GmailClient",
    "GmailError",
    "GmailHistoryExpired",
    "GmailSettings",
    "GmailSync",
    "GmailSyncState",
    "authorization_url",
    "create_sync_table",
    "decode_push",
    "exchange_code",
    "get_credentials",
    "handle_push",
    "parse_message",
    "save_credentials",
]
