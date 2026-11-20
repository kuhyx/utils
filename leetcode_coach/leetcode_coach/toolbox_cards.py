"""Toolbox entries as post-mortem cards, and the one way to grow the toolbox.

DOCS-coach-spec.md decision 11: post-mortem cards are property -> operation only.
The front lists an entry's properties, the back is its name, so the card asks
"which tool has exactly these properties?". All cards share the fixed slug
``toolbox``: the card builder derives a note's guid from (slug, front), so one
slug means one note per entry however many problems used it.

  python3 -m leetcode_coach.toolbox_cards cards <name|alias>...   (stdout ->
      the JSON make_cards.py reads; pipe it straight in)
  python3 -m leetcode_coach.toolbox_cards add <name> [--alias A]... --property P...
      [--define "P=meaning"]...   (a property the vocabulary lacks yet)

``add`` (``append_entry``) is the only writer of toolbox.json and the coach
calls it on its own judgement (kuhy may veto). It refuses unknown
properties, a name or alias already taken, and a property set that nests with
an existing entry's (that card would have two right answers). Its printed
lines are its interface (T201 exemption in pyproject.toml).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from leetcode_coach import card_rules, toolbox

_logger = logging.getLogger(__name__)

SLUG = "toolbox"
FRONT_PREFIX = "Toolbox: "


def _key(text: str) -> str:
    """Case- and space-insensitive form of a name or alias."""
    return " ".join(text.split()).casefold()


def find(data: dict[str, Any], name: str) -> dict[str, Any]:
    """The entry called ``name`` (or with that alias); KeyError if there is none."""
    wanted = _key(name)
    for entry in data["entries"]:
        if wanted in {_key(n) for n in [entry["name"], *entry["aliases"]]}:
            return dict(entry)
    msg = f"{name!r} is not in the toolbox"
    raise KeyError(msg)


def entry_card(entry: dict[str, Any]) -> card_rules.Card:
    """The property -> operation card for one entry."""
    front = FRONT_PREFIX + ", ".join(entry["properties"]) + "?"
    return {"front": front, "back": str(entry["name"])}


def cards_for(names: list[str], path: Path | None = None) -> list[card_rules.Card]:
    """Cards for the named entries, in the order given."""
    data = toolbox.load(path)
    return [entry_card(find(data, name)) for name in names]


def _problems(
    data: dict[str, Any], name: str, aliases: list[str], properties: list[str]
) -> list[str]:
    """Every reason the candidate entry may not be added (empty = ok)."""
    if not name.strip():
        return ["empty name"]
    if not properties:
        return ["no properties"]
    problems: list[str] = []
    if unknown := sorted(set(properties) - set(data["properties"])):
        problems.append("unknown properties: " + ", ".join(unknown))
    if len(set(properties)) != len(properties):
        problems.append("a property is listed twice")
    taken = {_key(n) for e in data["entries"] for n in [e["name"], *e["aliases"]]}
    if clash := [n for n in [name, *aliases] if _key(n) in taken]:
        problems.append(f"already in the toolbox: {', '.join(clash)}")
    if problems:
        return problems
    mine = set(properties)
    for entry in data["entries"]:
        theirs = set(entry["properties"])
        if mine <= theirs or theirs <= mine:
            problems.append(f"property set nests with {entry['name']!r}")
    candidate = {"name": name, "aliases": aliases, "properties": properties}
    problems += card_rules.validate(SLUG, [entry_card(candidate)])
    return problems


def _definition_problems(
    vocab: dict[str, str], properties: list[str], definitions: dict[str, str]
) -> list[str]:
    """Why the new vocabulary entries may not be added (empty = ok)."""
    problems = [f"already defined: {p}" for p in definitions if p in vocab]
    problems += [f"empty meaning: {p}" for p, m in definitions.items() if not m.strip()]
    unused = [p for p in definitions if p not in properties]
    problems += [f"defined but not used: {p}" for p in unused]
    return problems


def append_entry(
    name: str,
    aliases: list[str],
    properties: list[str],
    *,
    path: Path | None = None,
    definitions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Append one entry to toolbox.json; ValueError if it is refused.

    ``definitions`` adds properties the vocabulary lacks yet (name -> meaning);
    each must be new and used by this entry, so the vocabulary never holds an
    unused or silently redefined property.
    """
    target = toolbox.TOOLBOX_PATH if path is None else path
    data = toolbox.load(target)
    definitions = definitions or {}
    if problems := _definition_problems(data["properties"], properties, definitions):
        raise ValueError("; ".join(problems))
    data["properties"].update(definitions)
    if problems := _problems(data, name, aliases, properties):
        raise ValueError("; ".join(problems))
    entry = {"name": name.strip(), "aliases": aliases, "properties": properties}
    data["entries"].append(entry)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    # Written beside the target and renamed over it: a crash mid-write must
    # not leave kuhy's reviewed toolbox half a file.
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".toolbox-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    Path(tmp).replace(target)
    return entry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="toolbox_cards")
    sub = parser.add_subparsers(dest="command", required=True)
    cards = sub.add_parser("cards", help="print make_cards.py input for entries")
    cards.add_argument("names", nargs="+")
    add = sub.add_parser("add", help="append a new toolbox entry")
    add.add_argument("name")
    add.add_argument("--alias", action="append", default=[])
    add.add_argument("--property", action="append", default=[], required=True)
    add.add_argument("--define", action="append", default=[], metavar="P=MEANING")
    return parser


def _parse_definitions(raw: list[str]) -> dict[str, str]:
    """``["P=meaning", ...]`` as a dict; ValueError on an item without ``=``."""
    if bad := [item for item in raw if "=" not in item]:
        msg = "--define takes name=meaning, got: " + ", ".join(bad)
        raise ValueError(msg)
    pairs = (item.split("=", 1) for item in raw)
    return {name.strip(): meaning.strip() for name, meaning in pairs}


def main(argv: list[str]) -> int:
    """`cards` prints builder input; `add` appends a new entry."""
    args = _parser().parse_args(argv)
    if args.command == "cards":
        try:
            cards = cards_for(args.names)
        except KeyError as exc:
            _logger.warning("cards for an unknown entry: %s", exc)
            print(exc.args[0], file=sys.stderr)
            return 1
        print(json.dumps({"slug": SLUG, "cards": cards}, ensure_ascii=False))
        return 0
    try:
        definitions = _parse_definitions(args.define)
        entry = append_entry(
            args.name, args.alias, args.property, definitions=definitions
        )
    except ValueError as exc:
        _logger.warning("toolbox entry refused: %s", exc)
        print(f"not added: {exc}", file=sys.stderr)
        return 1
    print(f"added {entry['name']!r}: {', '.join(entry['properties'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
