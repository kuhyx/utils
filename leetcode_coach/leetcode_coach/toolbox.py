"""The operation toolbox (TODO-coach.md decision 9), read from ``toolbox.json``.

Schema: ``{"entries": [{"name", "aliases": [...], "properties": [...]}],
"properties": {"<prop>": "<one-line meaning>"}}``. Every entry property is a
key of ``properties``: the vocabulary is fixed, so the requirement checker and
the post-mortem cards speak the same words. kuhy reviews the JSON file itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TOOLBOX_PATH = Path(__file__).with_name("toolbox.json")


def load(path: Path | None = None) -> dict[str, Any]:
    """The parsed toolbox; ``path`` defaults to the shipped file at call time."""
    source = TOOLBOX_PATH if path is None else path
    data: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
    return data
