"""Turning a Firebase auth response into a message, and reading its verdict.

Split from :mod:`crdt_sync._firebase_auth`, which keeps the token provider.
identitytoolkit reports failures as a nested JSON error whose useful part is
buried; these turn that into something a log line can carry, and decide
whether the failure is permanent (the refresh token is dead and the user must
sign in again) or worth retrying.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from crdt_sync._remote import RemoteSyncError

if TYPE_CHECKING:
    import requests as _requests


class FirebaseAuthError(RemoteSyncError):
    """Raised for an authentication failure the caller must not ignore.

    A :class:`crdt_sync.RemoteSyncError` so callers that only care about
    "sync is broken" can catch one type, while a settings screen can single
    this out to say "your password is wrong" rather than "the network is
    down".
    """

def _reason(response: _requests.Response) -> str:
    """Return Google's machine-readable error reason, in parentheses.

    Pulls ``INVALID_PASSWORD`` / ``TOKEN_EXPIRED`` / ``USER_DISABLED`` out of
    the body so the raised message says what actually went wrong rather than
    just reporting a status code.
    """
    try:
        data = response.json()
    except ValueError:
        # A non-JSON body (a proxy error page, say): the status code is all
        # the detail there is.
        return ""
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, dict):
        return f" ({error.get('message')})"
    if isinstance(error, str):
        return f" ({error})"
    return ""


#: Reasons that mean the refresh token is permanently dead. Only these clear
#: the session: a network error or a 5xx must not, because a device that signs
#: itself out whenever the wifi drops needs a manual sign-in to recover, which
#: is a worse failure than the stale banner this guards against.
_TERMINAL_AUTH_REASONS = (
    "TOKEN_EXPIRED",
    "USER_DISABLED",
    "USER_NOT_FOUND",
    "INVALID_REFRESH_TOKEN",
    "INVALID_GRANT_TYPE",
    "MISSING_REFRESH_TOKEN",
)


def _is_revoked(error: FirebaseAuthError) -> bool:
    """Return whether ``error`` means the refresh token is permanently dead."""
    message = str(error)
    return any(reason in message for reason in _TERMINAL_AUTH_REASONS)
