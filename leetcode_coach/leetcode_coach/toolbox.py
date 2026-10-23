"""The toolbox of operations, loaded from ``toolbox.json`` next to this file.

Schema: ``{"entries": [{"name", "aliases", "properties"}], "properties":
{"<prop>": "<one-line meaning>"}}``. The entries feed the leak bounce (no
entry may be named before kuhy's first code) and the property vocabulary is
the only thing the requirement checker may say back. The data is
TODO-coach.md item 9's; this module only reads it.

An unreadable or malformed file is an empty toolbox plus a warning: both
consumers then fail open (nothing bounced, req check ``unverified``) rather
than locking kuhy out of a session over a typo in a JSON file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path

_LOG = logging.getLogger(__name__)

TOOLBOX_PATH = Path(__file__).with_name("toolbox.json")


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


def _parse(raw: object) -> Toolbox:
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


def load(path: Path | None = None) -> Toolbox:
    """The toolbox at `path` (default ``toolbox.json``), or an empty one."""
    target = TOOLBOX_PATH if path is None else path
    try:
        return _parse(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as exc:
        _LOG.warning("toolbox %s is unusable, checks fail open: %s", target, exc)
        return Toolbox()
