# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""The tutor's layout (its DOCS-contract §12): the reference the vectors pin."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rtdb_relay.layout import Layout

VECTORS: dict[str, Any] = json.loads(
    (Path(__file__).parent / "data" / "e2e_vectors.json").read_text()
)
TUTOR = Layout(
    root="tutor/v1-e2e",
    clear=("meta", "rev", "migration", "requests/*/claim", "sessions/*/progress/rid"),
    units={
        "live": frozenset(),
        "prefs/*": frozenset(),
        "stats/*": frozenset(),
        "presence/workers/*": frozenset({"beat"}),
        "presence/clients/*": frozenset({"seen"}),
        "uploads/*/*": frozenset(),
        "requests/*/req": frozenset({"created"}),
        "requests/*/result": frozenset({"at"}),
        "sessions/*/meta/*": frozenset(),
        "sessions/*/msgs/*": frozenset(),
        "sessions/*/receipts/*": frozenset(),
        "sessions/*/user/*": frozenset(),
        "sessions/*/progress/steps/*": frozenset(),
        "session_index/*": frozenset(),
        "subjects/*/meta": frozenset(),
        "subjects/*/plan": frozenset(),
        "subjects/*/cards": frozenset(),
        "subjects/*/concepts": frozenset(),
        "log/*/*": frozenset(),
        "feedback/*": frozenset(),
    },
)
