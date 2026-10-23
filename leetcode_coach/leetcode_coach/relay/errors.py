"""The one exception a request handler raises to answer with an error result."""

from __future__ import annotations


class CoachError(Exception):
    """Answer the request with ``code``; the message is shown to kuhy."""

    def __init__(
        self, message: str, *, code: str, retry: bool = False, **extra: object
    ) -> None:
        """Keep the result fields (section 2's error codes)."""
        super().__init__(message)
        self.code = code
        self.retry = retry
        self.extra = extra
