#!/usr/bin/python3
"""Turn a /leetcode post-mortem into an Anki deck file (.apkg).

Usage: make_cards.py [--dry-run | --replace] <cards.json | ->   (- = stdin)
  {"slug": "timeout-cancellation",
   "cards": [{"front": "JS: cancel a pending setTimeout?",
              "back": "clearTimeout(id)"}]}

The shape rules (word caps, coin-flip and placeholder fronts) live in
`card_rules.py`; a violation fails the run (exit 1) and names the offender.
Deck and model ids are fixed and the note guid is derived from (slug, front),
so re-importing a regenerated file updates the same notes instead of
duplicating them. Fields are HTML, so text is escaped (`a<b` would vanish).

  --dry-run  validate and print the table; no log, no delivery
  --replace  make this the problem's whole card set: notes of the slug that
             are not in the input get deleted. Needs Anki open (AnkiConnect);
             an .apkg import cannot delete, so without it the run fails.

Delivery, in order of preference:
  1. Anki desktop is open with AnkiConnect -> notes are upserted directly and
     a sync to AnkiWeb is triggered, so AnkiDroid gets them at its next open.
  2. Otherwise -> ~/data/learn/leetcode/anki/<date>-<slug>.apkg, imported by
     `anki <file>` (which also starts Anki).
Either way the cards are appended to ~/data/learn/leetcode/cards.tsv.

Runs on the system python (genanki in its user site, installed by
install.sh); it used to be a `uv run --script` file. Its printed table and
delivery line ARE its interface (T201 exemption in pyproject.toml).
"""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
import shlex
import sys
from typing import Protocol, cast

import genanki

from leetcode_coach import anki_connect, card_rules, session_log

DECK_ID = 1_695_042_117_001  # fixed: every session's file imports into the same deck
MODEL_ID = 1_695_042_117_002
DECK_NAME = "LeetCode"
OUT_DIR = Path.home() / "data" / "learn" / "leetcode"  # ~/data: an allowed root bucket
FLAGS = ("--dry-run", "--replace")

MODEL_NAME = "LeetCode coach (basic)"
FIELDS = ["Front", "Back", "Problem"]
QFMT = "{{Front}}<br><br><span style='font-size:70%;color:#888'>{{Problem}}</span>"
AFMT = "{{FrontSide}}<hr id=answer>{{Back}}"
CSS = ".card { font-family: sans-serif; font-size: 22px; text-align: center; }"

MODEL = genanki.Model(
    MODEL_ID,
    MODEL_NAME,
    fields=[{"name": f} for f in FIELDS],
    templates=[{"name": "Card 1", "qfmt": QFMT, "afmt": AFMT}],
    css=CSS,
)


class Note(Protocol):
    """The part of `genanki.Note` this module relies on (genanki is untyped)."""

    @property
    def guid(self) -> str:
        """Stable id: re-importing the same (slug, front) updates the note."""

    @property
    def fields(self) -> list[str]:
        """Front, Back, Problem -- HTML-escaped text."""

    @property
    def tags(self) -> list[str]:
        """Anki tags."""


def card_note(front: str, back: str, slug: str) -> Note:
    """A note whose guid ignores escaping, so a regenerated deck updates it."""
    guid = genanki.guid_for(slug, html.unescape(front))
    note = genanki.Note(
        model=MODEL, fields=[front, back, slug], tags=["leetcode", slug], guid=guid
    )
    return cast("Note", note)


def _log(slug: str, cards: list[card_rules.Card], today: str) -> None:
    """Append the cards to the plain-text history."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "cards.tsv").open("a", encoding="utf-8") as fh:
        for c in cards:
            row = (today, slug, c["front"].strip(), c["back"].strip())
            fh.write("\t".join(row) + "\n")


def push_direct(slug: str, cards: list[card_rules.Card], *, replace: bool) -> str:
    """AnkiConnect path: upsert into the open desktop collection, then sync."""
    anki_connect.ensure_model(MODEL_NAME, FIELDS, QFMT, AFMT, CSS)
    added, updated, deleted = anki_connect.sync_notes(
        DECK_NAME, MODEL_NAME, slug, card_rules.escaped(cards), replace=replace
    )
    anki_connect.sync()
    return (
        f"{added} added, {updated} updated, {deleted} deleted in {DECK_NAME!r}; "
        "AnkiWeb sync requested (lands on the phone at AnkiDroid's next sync)"
    )


def build_apkg(slug: str, cards: list[card_rules.Card], today: str) -> Path:
    """Offline path: write a deck file that `anki <file>` imports."""
    deck = genanki.Deck(DECK_ID, DECK_NAME)
    for c in card_rules.escaped(cards):
        deck.add_note(card_note(c["front"], c["back"], slug))
    out_dir = OUT_DIR / "anki"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{today}-{slug}.apkg"
    genanki.Package(deck).write_to_file(str(out))
    return out


def deliver(
    slug: str,
    cards: list[card_rules.Card],
    *,
    replace: bool = False,
    online: bool | None = None,
) -> str:
    """Log already-validated `cards` and deliver them; the delivery line.

    AnkiConnect when Anki is open, else an .apkg. The coach relay calls this
    in-process (no ``postmortem`` here: the caller logs it to its own log).
    """
    today = dt.datetime.now(tz=dt.UTC).date().isoformat()
    _log(slug, cards, today)
    if anki_connect.available() if online is None else online:
        done = push_direct(slug, cards, replace=replace)
        return f"{len(cards)} cards -> Anki desktop: {done}"
    out = build_apkg(slug, cards, today)
    return (
        f"{len(cards)} cards -> {out} (Anki desktop not open). Import with:\n"
        f"anki {shlex.quote(str(out))}"
    )


def _usage() -> str:
    """The `Usage:` line of this module's docstring."""
    return (__doc__ or "").strip().splitlines()[2]


def main() -> int:
    """Validate the cards on argv/stdin, then deliver them; 0 on success."""
    args = sys.argv[1:]
    flags = {a for a in args if a in FLAGS}
    rest = [a for a in args if a not in FLAGS]
    if len(rest) != 1 or len(flags) > 1:
        print(_usage(), file=sys.stderr)
        return 1
    src = rest[0]
    raw = sys.stdin.read() if src == "-" else Path(src).read_text(encoding="utf-8")
    spec = json.loads(raw)
    slug, cards = str(spec.get("slug", "")).strip(), list(spec.get("cards", []))
    if errors := card_rules.validate(slug, cards):
        print("cards rejected:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    if "--dry-run" in flags:
        print(card_rules.table(cards))
        return 0
    replace = "--replace" in flags
    online = anki_connect.available()
    if replace and not online:
        print(
            "--replace needs Anki open (AnkiConnect); nothing changed", file=sys.stderr
        )
        return 1
    print(card_rules.table(cards))
    print(deliver(slug, cards, replace=replace, online=online))
    # Delivered: the post-mortem is done. Re-test completion and "solved"
    # (progress.py) read this event from the REPL's session log.
    session_log.append_current("postmortem", cards=len(cards))
    return 0


if __name__ == "__main__":
    sys.exit(main())
