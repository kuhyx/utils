# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""Sealing writes and opening reads of an app's RTDB tree.

A unit is stored as ``{"_e2e": <XChaCha20-Poly1305 blob>, <clear siblings>}``;
the blob is crdt_sync's ``E2eCipher`` with the unit's full path as AAD, so
a blob copied to another path does not open. The byte format is pinned by
``tests/data/e2e_vectors.json`` (the tutor's contract vectors).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Final

from crdt_sync import E2eCipher, E2eDecryptError

from rtdb_relay.layout import E2eLayoutError, Layout, parts_of

if TYPE_CHECKING:
    from rtdb_relay.layout import Rule

SEALED: Final = "_e2e"
_logger = logging.getLogger(__name__)


def pruned(value: object) -> object:
    """``value`` as RTDB would keep it: no null members, no empty objects."""
    if not isinstance(value, dict):
        return value
    out = {k: pruned(v) for k, v in value.items()}
    return {k: v for k, v in out.items() if v is not None} or None


def dumps(value: object) -> str:
    """Compact JSON, UTF-8 kept (the sealed plaintext format)."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


class Sealer:
    """Seals writes and opens reads of the tree ``layout`` describes."""

    def __init__(
        self, cipher: E2eCipher, layout: Layout, root: str | None = None
    ) -> None:
        """Use ``cipher`` for every unit; AAD prefix ``root`` (default the layout's)."""
        self._cipher = cipher
        self.layout = layout
        self.root = layout.root if root is None else root

    def classify(self, parts: list[str]) -> Rule:
        """The layout's rule for ``parts``."""
        return self.layout.classify(parts)

    def unit_path(self, path: str) -> str | None:
        """The sealed unit ``path`` lies strictly below, or ``None``."""
        return self.layout.unit_path(path)

    def _aad(self, parts: list[str]) -> str:
        return "/".join([self.root, *parts])

    # -- writes ---------------------------------------------------------------
    def seal(self, path: str, value: object) -> object:
        """``value`` as it may be stored at ``path``; refuses unknown paths."""
        return self._seal(parts_of(path), value)

    def seal_patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """A PATCH body for ``path``: each (multi-segment) key sealed on its own."""
        if self.classify(parts_of(path)).kind in {"unit", "below"}:
            msg = f"PATCH into sealed unit {path}"
            raise E2eLayoutError(msg)
        base = parts_of(path)
        return {k: self._seal([*base, *parts_of(k)], v) for k, v in body.items()}

    def _seal(self, parts: list[str], value: object) -> object:
        rule = self.classify(parts)
        if rule.kind == "clear" or value is None:
            return value
        if rule.kind == "unit":
            return self._seal_unit(parts, value, rule.keep)
        if rule.kind == "struct" and isinstance(value, dict):
            return {k: self._seal([*parts, *parts_of(k)], v) for k, v in value.items()}
        where = "/".join(parts) or "/"
        msg = f"no e2e rule for a {type(value).__name__} at {where} ({rule.kind})"
        raise E2eLayoutError(msg)

    def _seal_unit(
        self, parts: list[str], value: object, keep: frozenset[str]
    ) -> object:
        value = pruned(value)
        if value is None:
            return None  # RTDB stores no null and no empty object
        clear: dict[str, Any] = {}
        if isinstance(value, dict) and keep:
            clear = {k: v for k, v in value.items() if k in keep}
            value = {k: v for k, v in value.items() if k not in keep}
        blob = self._cipher.seal(dumps(value), path=self._aad(parts))
        return {SEALED: blob, **clear}

    # -- reads ----------------------------------------------------------------
    def open(self, path: str, value: object) -> object:
        """``value`` read at ``path``, every unit in it opened.

        A unit that does not open (tampered, other key) reads as absent.
        Legacy plaintext (a unit without ``_e2e``) is returned as stored.
        """
        return self._open(parts_of(path), value)

    def _open(self, parts: list[str], value: object) -> object:
        rule = self.classify(parts)
        if rule.kind == "unit":
            return self._open_unit(parts, value)
        if rule.kind == "below":
            msg = f"read below sealed unit: {'/'.join(parts)}"
            raise E2eLayoutError(msg)
        if rule.kind == "struct" and isinstance(value, dict):
            out = {k: self._open([*parts, k], v) for k, v in value.items()}
            return {k: v for k, v in out.items() if v is not None}
        if rule.kind == "struct" and isinstance(value, list):
            return [self._open([*parts, str(i)], v) for i, v in enumerate(value)]
        return value

    def _open_unit(self, parts: list[str], value: object) -> object:
        if not isinstance(value, dict) or not isinstance(value.get(SEALED), str):
            return value  # legacy plaintext, accepted during a migration
        clear = {k: v for k, v in value.items() if k != SEALED}
        try:
            text = self._cipher.open(value[SEALED], path=self._aad(parts))
            data = json.loads(text)
        except E2eDecryptError, ValueError:
            _logger.warning("undecryptable node %s dropped", "/".join(parts))
            return None
        return {**data, **clear} if isinstance(data, dict) else data
