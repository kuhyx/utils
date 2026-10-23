"""The seven request kinds and their limits (DOCS-coach-relay.md 2 and 4).

`parse` is the only door into the relay: a request is checked here, field by
field, before anything builds a path or reaches a model. Unknown fields are
dropped, a kind outside the seven is never run, and an id is regex-checked
first. A bad ``rid`` raises `BadRidError` (it gets no result at all: there is
nowhere safe to put one); anything else wrong is `BadRequestError`, answered
``bad_request``.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Final, NoReturn

KINDS: Final = (
    "session_start",
    "session_end",
    "chat",
    "grade_step",
    "hint",
    "reveal",
    "run_code",
)
RID_RE: Final = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")
"""A ULID: 26 Crockford base-32 characters (no I, L, O, U)."""
SID_RE: Final = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")
DEV_RE: Final = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
SLUG_RE: Final = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
MAX_SLUG: Final = 100
MAX_TEXT_BYTES: Final = 8192
MAX_REQ_BYTES: Final = 16 * 1024
MAX_PICKS: Final = 30
MAX_PICK_CHARS: Final = 64
GRADED_STEPS: Final = (1, 2, 3, 5)
TOOLBOX_STEP: Final = 3
ALL_STEPS: Final = range(1, 6)
RETRYABLE: Final = frozenset({"rate_limited", "model_error"})


class BadRidError(ValueError):
    """The rid is not a ULID: the request gets no result anywhere."""


class BadRequestError(ValueError):
    """Anything else wrong with a request; answered ``bad_request``."""


@dataclass(frozen=True)
class Request:
    """One validated request: only the fields its kind takes survive."""

    rid: str
    kind: str
    dev: str
    body: dict[str, Any]
    transport: str
    """``desktop`` (loopback API) or ``phone`` (RTDB)."""


def _bad(message: str) -> NoReturn:
    raise BadRequestError(message)


def _sid(body: dict[str, Any]) -> dict[str, Any]:
    sid = body.get("session")
    if not isinstance(sid, str) or not SID_RE.fullmatch(sid):
        _bad("session must be a session id")
    return {"session": sid}


def _text(body: dict[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        _bad(f"{key} must be a non-empty string")
    if len(value.encode()) > MAX_TEXT_BYTES:
        _bad(f"{key} is over {MAX_TEXT_BYTES} bytes")
    return value


def _picks(body: dict[str, Any]) -> list[str]:
    picks = body.get("picks")
    if not isinstance(picks, list) or len(picks) > MAX_PICKS:
        _bad(f"picks must be a list of at most {MAX_PICKS} names")
    if not all(isinstance(p, str) and 0 < len(p) <= MAX_PICK_CHARS for p in picks):
        _bad(f"every pick must be a name of at most {MAX_PICK_CHARS} chars")
    return picks


def _grade(body: dict[str, Any]) -> dict[str, Any]:
    step = body.get("step")
    if isinstance(step, bool) or not isinstance(step, int) or step not in ALL_STEPS:
        _bad("step must be 1 to 5")
    out: dict[str, Any] = {**_sid(body), "step": step}
    if "force" in body:
        if body["force"] is not True:
            _bad("force must be true when given")
        return {**out, "force": True}
    if step not in GRADED_STEPS:
        _bad("step 4 is never graded: it passes on a LeetCode Accepted")
    if step == TOOLBOX_STEP:  # it takes picks; the others take text
        return {**out, "picks": _picks(body)}
    return {**out, "answer": _text(body, "answer")}


def _body(kind: str, body: dict[str, Any]) -> dict[str, Any]:
    if kind == "session_start":
        slug = body.get("slug")
        if not isinstance(slug, str) or len(slug) > MAX_SLUG:
            _bad("slug must be a LeetCode slug")
        if not SLUG_RE.fullmatch(slug):
            _bad("slug must be a LeetCode slug")
        return {"slug": slug}
    if kind == "chat":
        return {**_sid(body), "text": _text(body, "text")}
    if kind == "run_code":
        return {**_sid(body), "code": _text(body, "code")}
    if kind == "grade_step":
        return _grade(body)
    return _sid(body)


def _no_rid(message: str) -> NoReturn:
    raise BadRidError(message)


def parse(raw: object, transport: str) -> Request:
    """The validated request in `raw` (a decoded ``req`` object).

    Raises:
        BadRidError: when there is no valid rid to answer under.
        BadRequestError: for every other problem.
    """
    rid = raw.get("rid") if isinstance(raw, dict) else None
    if not isinstance(raw, dict) or not isinstance(rid, str):
        _no_rid("a request needs a rid")
    if not RID_RE.fullmatch(rid):
        _no_rid("the rid is not a ULID")
    if len(json.dumps(raw, ensure_ascii=False).encode()) > MAX_REQ_BYTES:
        _bad(f"the request is over {MAX_REQ_BYTES} bytes")
    kind, dev, body = raw.get("kind"), raw.get("dev"), raw.get("body")
    if kind not in KINDS:
        _bad("unknown request kind")
    if not isinstance(dev, str) or not DEV_RE.fullmatch(dev):
        _bad("dev must be the app's install uuid")
    if not isinstance(body, dict):
        _bad("body must be an object")
    return Request(rid, str(kind), dev, _body(str(kind), body), transport)


def ok(data: dict[str, Any], *, at: int, state_rev: int) -> dict[str, Any]:
    """A success result."""
    return {"ok": True, "at": at, "state_rev": state_rev, "data": data}


def failure(
    code: str, error: str, *, at: int, retry: bool = False, **extra: object
) -> dict[str, Any]:
    """An error result; `error` is shown to kuhy as it stands."""
    return {
        "ok": False,
        "at": at,
        "code": code,
        "error": error,
        "retry": retry,
        **extra,
    }


def ok_retryable(code: str) -> bool:
    """Whether an error with `code` is one kuhy resends (as a NEW rid)."""
    return code in RETRYABLE
