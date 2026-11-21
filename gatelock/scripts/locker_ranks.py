#!/usr/bin/env python3
# Copyright (c) 2026 Krzysztof Rudnicki
"""The lock order kuhy fixed on 2026-11-21, and checks that the lockers keep it.

``verify_all_lockers.py`` starts one child per entry in :data:`LOCKERS` at the
rank written here. That only proves this table, so :func:`rank_drift` also
imports each locker's own rank constant (as ``/usr/bin/python3`` sees it, the
deployment path) and reports any that differ. A locker that is not installed
is skipped, not failed: this also runs on machines without the lockers.
"""

from __future__ import annotations

import importlib
from itertools import pairwise
import json
import sys
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

LOCKERS: Final = {  # gatelock app -> rank; see each repo's DOCS-lock-order.md
    "screen_locker": 200,
    "book_guard": 175,
    "tutor_gate": 150,
    "diet_guard": 130,
    "focus_guard": 128,
    "leetcode_guard": 125,
}
REQUIRED_ORDER: Final = (  # kuhy's order: workout, book, tutor, diet, leetcode
    "screen_locker",
    "book_guard",
    "tutor_gate",
    "diet_guard",
    "leetcode_guard",
)
SOURCES: Final = {  # app -> (module, constant) holding its real rank
    "screen_locker": ("gatelock", "RANK_SCREEN_LOCKER"),
    "book_guard": ("book_guard._constants", "RANK_BOOK_GUARD"),
    "tutor_gate": ("tutor.gate_lock", "RANK_TUTOR_EVENING"),
    "diet_guard": ("diet_guard._constants", "RANK_DIET_GUARD"),
    "focus_guard": ("focus_guard._constants", "RANK_FOCUS_GUARD"),
    "leetcode_guard": ("leetcode_guard._constants", "RANK_LEETCODE_GUARD"),
}


def order_holds() -> bool:
    """Whether :data:`LOCKERS` ranks kuhy's order strictly falling."""
    ranks = [LOCKERS[app] for app in REQUIRED_ORDER]
    return all(a > b for a, b in pairwise(ranks))


def rank_drift() -> tuple[list[str], list[str]]:
    """(mismatches, skipped): installed ranks that differ from the table."""
    bad: list[str] = []
    skipped: list[str] = []
    for app, (module, name) in SOURCES.items():
        try:
            real = getattr(importlib.import_module(module), name, None)
        except ImportError as exc:
            skipped.append(f"{app} ({exc})")
            continue
        if real != LOCKERS[app]:
            bad.append(f"{app}: installed {real}, table {LOCKERS[app]}")
    return bad, skipped


def firmness_defeats(claims_dir: Path) -> list[str]:
    """Pairs where a higher-ranked claim locks less firmly than a lower one.

    gatelock lets such a lower lock arm anyway (rank never weakens a lock), so
    each pair listed here is a place the order does not hold.
    """
    claims = [json.loads(p.read_text()) for p in sorted(claims_dir.glob("*.json"))]
    pairs: list[str] = []
    for hi in claims:
        for lo in claims:
            weaker = (hi["grab"] == "local" and lo["grab"] == "global") or (
                lo["disable_vt"] and not hi["disable_vt"]
            )
            if hi["rank"] > lo["rank"] and weaker:
                pairs.append(f"{hi['app']} ({hi['rank']}) > {lo['app']} ({lo['rank']})")
    return pairs


if __name__ == "__main__":
    # Fast check without an X server: the table's order and the installed ranks.
    drifted, missing = rank_drift()
    sys.stdout.write(
        f"order holds: {order_holds()}\ndrift: {drifted}\nskipped: {missing}\n"
    )
    sys.exit(0 if order_holds() and not drifted else 1)
