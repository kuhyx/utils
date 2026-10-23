r"""Which toolbox entries a coach reply names (TODO-coach.md decision 7).

Until kuhy's first code, a reply that names an operation from the toolbox --
its name or any alias, e.g. "XOR", "^", "hash map" -- hands over step 3 of the
method (searching the toolbox by properties). Shared by the Stop hook
(`stop_gate`) and the offline coach (`local_coach`), so both judge alike.

An entry kuhy (or the problem statement) already named is free for the whole
session, under every alias: after "is it XOR?" the honest answer has to be
able to say XOR, or the rewrite can never pass and the gate loops.

Matching is case-insensitive on whole tokens. ``\b`` does not work next to a
symbol alias like ``^``, so the boundary is "no word character either side":
"a ^ b" matches, "2^3" (a power) and "xorshift" do not.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from leetcode_coach.toolbox import Toolbox


def _pattern(name: str) -> re.Pattern[str]:
    words = r"\s+".join(re.escape(w) for w in name.split())
    return re.compile(rf"(?<!\w){words}(?!\w)", re.IGNORECASE)


def _named(text: str, names: tuple[str, ...]) -> bool:
    return any(_pattern(n).search(text) for n in names if n.strip())


def leaked_names(reply: str, allowed: list[str], box: Toolbox) -> list[str]:
    """Entry names in `reply` that nothing in `allowed` already named."""
    seen = "\n".join(allowed)
    return [
        e.name
        for e in box.entries
        if _named(reply, e.names()) and not _named(seen, e.names())
    ]
