"""The commands and the method, written once.

The status app's Coach tab shows these next to an empty session list, and
``DOCS-how-to.md`` (which SKILL.md points at) quotes the same lines verbatim;
a test fails when the two differ, which is the point of having one module. Nothing
here names a toolbox operation: the Stop hook bounces that before kuhy's
first code, and the same words on a screen would teach skipping the search.

Stdlib only, like ``progress``: the status snapshot imports this every
minute on the system python.
"""

from __future__ import annotations

from typing import Any, NamedTuple


class Command(NamedTuple):
    """One thing kuhy can type, and what it does."""

    command: str
    meaning: str


class Step(NamedTuple):
    """One step of the method."""

    name: str
    text: str


COMMANDS = (
    Command(
        "leetcode --cluster <name>",
        "Serve the next problem of a concept cluster (a due re-test comes first).",
    ),
    Command("leetcode <url>", "Coach one problem, from its LeetCode URL or slug."),
    Command("leetcode due", "List the cold re-tests that are due."),
    Command(
        "leetcode report",
        "One row per session: requirements before code, hint rung, reveal.",
    ),
)
STEPS = (
    Step("Constraint", "Turn the hard constraint into a rule for the design."),
    Step(
        "Requirements",
        "List what the operation must do, as properties, never by name.",
    ),
    Step("Toolbox", "Search the toolbox for an operation with those properties."),
    Step("Post-mortem", "Say which hint gave which requirement, then make the cards."),
)
NEXT_NOTE = (
    "The command skips problems LeetCode already shows as Accepted, "
    "so it may serve a later one than listed here."
)


def cluster_command(name: str) -> str:
    """The command that starts cluster ``name``."""
    return f"leetcode --cluster {name}"


def retest_command(slug: str) -> str:
    """The command that starts the cold re-test of ``slug``."""
    return f"leetcode --retest {slug}"


def block(first_cluster: str | None) -> dict[str, Any]:
    """The snapshot's ``coach.how_to``; ``first_cluster`` names the first command."""
    return {
        "commands": [c._asdict() for c in COMMANDS],
        "steps": [s._asdict() for s in STEPS],
        "next_note": NEXT_NOTE,
        "first_command": (
            None if first_cluster is None else cluster_command(first_cluster)
        ),
    }
