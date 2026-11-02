"""The relay spawns nothing but claude and node (DOCS-coach-ui-spec.md decision 2).

The ledger boundary (no coach module imports leetcode_guard, the bridge names
only read-only guard modules) is ``test_guard_boundary.py``.
"""

from __future__ import annotations

from pathlib import Path
import re

import leetcode_coach

ROOT = Path(leetcode_coach.__file__).resolve().parent.parent


def test_no_relay_module_spawns_anything_but_claude_and_node() -> None:
    relay = ROOT / "leetcode_coach" / "relay"
    spawning = {
        p.name
        for p in relay.glob("*.py")
        if re.search(r"\bsubprocess\b|os\.system|os\.exec|Popen", p.read_text())
    }
    assert spawning == {"runcode.py"}  # claude runs via claude_cli.ask
