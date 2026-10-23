"""Push cards straight into the running Anki desktop via AnkiConnect.

Stdlib only. Anki must be open with the AnkiConnect add-on (2055492159);
`available()` is the probe, everything else assumes it. Notes are matched by
(deck, Problem, Front) so a re-run edits instead of duplicating, mirroring the
stable-guid behaviour of the .apkg path; `replace` also deletes dropped notes.
`sync()` pushes to AnkiWeb, which is what gets the cards onto AnkiDroid at its
next open.
"""

from __future__ import annotations

import html
import json
import logging
from typing import Any
import urllib.error
import urllib.request

_LOG = logging.getLogger(__name__)

URL = "http://127.0.0.1:8765"


class AnkiConnectError(RuntimeError):
    """AnkiConnect answered with an error field."""

    def __init__(self, action: str, error: object) -> None:
        """Name the action and the error AnkiConnect returned."""
        super().__init__(f"{action}: {error}")


def _call(action: str, **params: object) -> Any:
    """One AnkiConnect request; its `result`, or AnkiConnectError."""
    body = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # fixed localhost URL
        payload = json.load(resp)
    if payload.get("error"):
        raise AnkiConnectError(action, payload["error"])
    return payload.get("result")


def available() -> bool:
    """Whether Anki desktop is open with AnkiConnect answering."""
    try:
        return _call("version") is not None
    except (
        urllib.error.URLError,
        TimeoutError,
        ConnectionError,
        AnkiConnectError,
    ) as exc:
        _LOG.warning("AnkiConnect is not available: %s", exc)
        return False


def ensure_model(name: str, fields: list[str], qfmt: str, afmt: str, css: str) -> None:
    """Create the note type unless the collection already has it."""
    if name in _call("modelNames"):
        return
    _call(
        "createModel",
        modelName=name,
        inOrderFields=fields,
        css=css,
        cardTemplates=[{"Name": "Card 1", "Front": qfmt, "Back": afmt}],
    )


def _term(field: str, value: str) -> str:
    """Quote the WHOLE `field:value` term; quotes after the colon match nothing."""
    return '"' + field + ":" + value.replace('"', '\\"') + '"'


def _existing_by_front(deck: str, slug: str) -> dict[str, int]:
    r"""Map unescaped Front -> note id for every note of this problem.

    Diffing in Python, not via a Front search: Anki search treats `_ * \`
    specially and fields are stored HTML-escaped, so a search misses notes.
    """
    ids = _call("findNotes", query=f"{_term('deck', deck)} {_term('Problem', slug)}")
    infos = _call("notesInfo", notes=ids) if ids else []
    return {html.unescape(n["fields"]["Front"]["value"]): n["noteId"] for n in infos}


def _add(deck: str, model: str, slug: str, front: str, back: str) -> None:
    """Add one note and make sure it sits in `deck`."""
    note_id = _call(
        "addNote",
        note={
            "deckName": deck,
            "modelName": model,
            "fields": {"Front": front, "Back": back, "Problem": slug},
            "tags": ["leetcode", slug],
            "options": {"allowDuplicate": False, "duplicateScope": "deck"},
        },
    )
    # With Anki's "add to current deck" preference on, addNote lands in the
    # current deck regardless of deckName (seen on 25.09.2). Move explicitly.
    _call("changeDeck", cards=_call("findCards", query=f"nid:{note_id}"), deck=deck)


def sync_notes(
    deck: str, model: str, slug: str, cards: list[dict[str, str]], *, replace: bool
) -> tuple[int, int, int]:
    """Add or update one note per card (fields already HTML-escaped).

    With `replace`, notes of this problem whose Front is not in `cards` are
    deleted, so a rewritten deck does not keep the cards it dropped.
    Returns (added, updated, deleted).
    """
    _call("createDeck", deck=deck)
    existing = _existing_by_front(deck, slug)
    added = updated = 0
    keep: set[int] = set()
    for c in cards:
        front, back = c["front"], c["back"]
        note_id = existing.get(html.unescape(front))
        if note_id is not None:
            _call(
                "updateNoteFields",
                note={"id": note_id, "fields": {"Front": front, "Back": back}},
            )
            keep.add(note_id)
            updated += 1
            continue
        _add(deck, model, slug, front, back)
        added += 1
    stale = [i for i in existing.values() if i not in keep] if replace else []
    if stale:
        _call("deleteNotes", notes=stale)
    return added, updated, len(stale)


def sync() -> None:
    """Ask Anki to sync with AnkiWeb."""
    _call("sync")
