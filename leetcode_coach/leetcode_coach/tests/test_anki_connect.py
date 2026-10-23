"""Tests for the AnkiConnect side of the /leetcode card builder."""

from __future__ import annotations

import io
import json
from typing import Any, Self
import urllib.error
import urllib.request

import pytest

from leetcode_coach import anki_connect, card_rules


def _card(front: str, back: str = "x") -> dict[str, str]:
    return {"front": front, "back": back}


class FakeAnki:
    """Minimal in-memory AnkiConnect: notes keyed by id."""

    def __init__(self, notes: dict[int, tuple[str, str]]) -> None:
        self.notes = {i: {"Front": f, "Back": b} for i, (f, b) in notes.items()}
        self.deleted: list[int] = []
        self.next_id = 100

    def __call__(self, action: str, **p: Any) -> Any:
        if action == "findNotes":
            return list(self.notes)
        if action == "notesInfo":
            return [
                {
                    "noteId": i,
                    "fields": {k: {"value": v} for k, v in self.notes[i].items()},
                }
                for i in p["notes"]
            ]
        if action == "updateNoteFields":
            self.notes[p["note"]["id"]].update(p["note"]["fields"])
        elif action == "addNote":
            self.next_id += 1
            self.notes[self.next_id] = dict(p["note"]["fields"])
            return self.next_id
        elif action == "deleteNotes":
            self.deleted += p["notes"]
            for i in p["notes"]:
                del self.notes[i]
        elif action == "findCards":
            return [1]
        return None


def test_sync_notes_replace_keeps_matching_front_and_deletes_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeAnki({1: ("n & m?", "old"), 2: ("dropped?", "gone")})
    monkeypatch.setattr(anki_connect, "_call", fake)
    cards = card_rules.escaped([_card("n & m?", "new"), _card("added?", "a")])
    result = anki_connect.sync_notes("D", "M", "s", cards, replace=True)
    assert result == (1, 1, 1)
    assert fake.deleted == [2]
    assert fake.notes[1] == {"Front": "n &amp; m?", "Back": "new"}


def test_sync_notes_without_replace_deletes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeAnki({2: ("dropped?", "gone")})
    monkeypatch.setattr(anki_connect, "_call", fake)
    assert anki_connect.sync_notes("D", "M", "s", [_card("a?")], replace=False) == (
        1,
        0,
        0,
    )
    assert fake.deleted == []


def test_sync_notes_on_an_empty_problem_skips_notes_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeAnki({})
    monkeypatch.setattr(anki_connect, "_call", fake)
    assert anki_connect.sync_notes("D", "M", "s", [_card("a?")], replace=True) == (
        1,
        0,
        0,
    )


class FakeResponse(io.BytesIO):
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _serve(
    monkeypatch: pytest.MonkeyPatch, replies: dict[str, Any]
) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    def urlopen(req: Any, timeout: int) -> FakeResponse:
        body = json.loads(req.data)
        sent.append(body)
        reply = replies[body["action"]]
        if isinstance(reply, Exception):
            raise reply
        return FakeResponse(json.dumps(reply).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return sent


def test_call_available_ensure_model_and_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _serve(
        monkeypatch,
        {
            "version": {"result": 6, "error": None},
            "modelNames": {"result": ["Basic"], "error": None},
            "createModel": {"result": {}, "error": None},
            "sync": {"result": None, "error": None},
        },
    )
    assert anki_connect.available() is True
    anki_connect.ensure_model("M", ["F"], "q", "a", "css")
    anki_connect.sync()
    assert [b["action"] for b in sent] == [
        "version",
        "modelNames",
        "createModel",
        "sync",
    ]


def test_ensure_model_skips_existing_and_errors_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _serve(
        monkeypatch,
        {
            "modelNames": {"result": ["M"], "error": None},
            "deleteNotes": {"result": None, "error": "boom"},
            "version": urllib.error.URLError("refused"),
        },
    )
    anki_connect.ensure_model("M", ["F"], "q", "a", "css")
    assert [b["action"] for b in sent] == ["modelNames"]
    with pytest.raises(anki_connect.AnkiConnectError, match="deleteNotes: boom"):
        anki_connect._call("deleteNotes", notes=[1])
    assert anki_connect.available() is False
