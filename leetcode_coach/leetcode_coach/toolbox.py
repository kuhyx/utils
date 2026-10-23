"""The operation toolbox (TODO-coach.md decision 9), read from ``toolbox.json``.

Schema: ``{"entries": [{"name", "aliases": [...], "properties": [...]}],
"properties": {"<prop>": "<one-line meaning>"}}``. Every entry property is a
key of ``properties``: the vocabulary is fixed, so the requirement checker and
the post-mortem cards speak the same words. kuhy reviews the JSON file itself.

`load` is the raw parse (cards, clusters). `load_safe` is the typed view the
gates use -- the leak bounce (no entry named before kuhy's first code) and the
req checker (may only say vocabulary properties back). An unreadable or
malformed file is an empty `Toolbox` plus a warning there, so both gates fail
open (nothing bounced, req check ``unverified``) instead of locking kuhy out of
a session over a typo in a JSON file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from typing import Any

_LOG = logging.getLogger(__name__)

TOOLBOX_PATH = Path(__file__).with_name("toolbox.json")


def load(path: Path | None = None) -> dict[str, Any]:
    """The parsed toolbox; ``path`` defaults to the shipped file at call time."""
    source = TOOLBOX_PATH if path is None else path
    data: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
    return data


@dataclass(frozen=True)
class Entry:
    """One operation: how it is called and which properties it has."""

    name: str
    aliases: tuple[str, ...] = ()
    properties: tuple[str, ...] = ()

    def names(self) -> tuple[str, ...]:
        """The name first, then every alias."""
        return (self.name, *self.aliases)


@dataclass(frozen=True)
class Toolbox:
    """All entries plus the property vocabulary (name -> meaning)."""

    entries: tuple[Entry, ...] = ()
    properties: dict[str, str] = field(default_factory=dict)


def _strings(value: object, what: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        msg = f"{what} must be a list of strings"
        raise TypeError(msg)
    return tuple(value)


def _entry(raw: object) -> Entry:
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
        msg = "every entry needs a string name"
        raise TypeError(msg)
    return Entry(
        name=raw["name"],
        aliases=_strings(raw.get("aliases", []), "aliases"),
        properties=_strings(raw.get("properties", []), "properties"),
    )


def _typed(raw: object) -> Toolbox:
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
        msg = "the toolbox must be an object with an entries list"
        raise TypeError(msg)
    props = raw.get("properties", {})
    if not isinstance(props, dict) or not all(
        isinstance(v, str) for v in props.values()
    ):
        msg = "properties must map each name to a one-line meaning"
        raise TypeError(msg)
    return Toolbox(tuple(_entry(e) for e in raw["entries"]), dict(props))


def load_safe(path: Path | None = None) -> Toolbox:
    """The typed toolbox at `path` (default ``toolbox.json``), or an empty one."""
    target = TOOLBOX_PATH if path is None else path
    try:
        return _typed(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as exc:
        _LOG.warning("toolbox %s is unusable, checks fail open: %s", target, exc)
        return Toolbox()
