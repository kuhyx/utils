# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""A local copy of a streamed RTDB node, kept current from put/patch events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rtdb_relay.sse import Event


def _parts(path: str) -> list[str]:
    return [p for p in path.split("/") if p]


def _set(tree: dict[str, Any], parts: list[str], value: object) -> dict[str, Any]:
    """``tree`` with ``value`` at ``parts`` (``None`` deletes, empty parents go)."""
    head, rest = parts[0], parts[1:]
    if rest:
        child = tree.get(head)
        value = _set(child if isinstance(child, dict) else {}, rest, value)
        if not value:
            value = None
    if value is None:
        tree.pop(head, None)
    else:
        tree[head] = value
    return tree


def apply(tree: dict[str, Any], event: Event) -> dict[str, Any]:
    """The mirrored node after ``event`` (a new dict on a root ``put``)."""
    parts = _parts(event.path)
    if event.kind == "put":
        if not parts:
            return event.data if isinstance(event.data, dict) else {}
        return _set(tree, parts, event.data)
    for key, value in (event.data or {}).items():
        tree = _set(tree, [*parts, *_parts(key)], value)
    return tree


def first_key(path: str) -> str | None:
    """The top-level key an event path touches (``None`` for the root)."""
    parts = _parts(path)
    return parts[0] if parts else None
