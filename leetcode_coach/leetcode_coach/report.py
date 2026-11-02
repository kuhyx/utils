"""`leetcode report`: one row per session file, for kuhy to read the method back.

Columns: req-before-code (``y``/``n``, ``-`` while there is no code yet),
the highest hint rung, whether ``reveal`` was typed, and every ``req_check``
verdict in order -- all of them, because "incomplete,incomplete,pass" is the
story, where the status app's reader keeps only the last one. Its stdout IS
its interface (T201 exemption in pyproject.toml); tests assert on it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from leetcode_coach import session_log

if TYPE_CHECKING:
    from pathlib import Path

COMMAND = "report"
RUNGS = ("H0", "H1", "H2", "H3")
WIDTHS = (36, 17, 10, 8)
HEADER = ("problem", "req-before-code", "max-rung", "reveal", "req_check")


def _line(cols: tuple[str, ...]) -> str:
    padded = [c.ljust(w) for c, w in zip(cols, WIDTHS, strict=False)]
    return "".join(padded) + cols[-1]


def _req_before_code(events: list[dict[str, Any]]) -> str:
    seen_req = False
    for event in events:
        if event.get("event") == "req":
            seen_req = True
        elif event.get("event") == "code":
            return "y" if seen_req else "n"
    return "-"


def row(path: Path) -> str:
    """The report line for one session file."""
    events = session_log.read(path)
    rungs = [
        RUNGS.index(e["rung"])
        for e in events
        if e.get("event") == "rung" and e.get("rung") in RUNGS
    ]
    verdicts = [str(e.get("verdict")) for e in events if e.get("event") == "req_check"]
    return _line(
        (
            path.stem,
            _req_before_code(events),
            RUNGS[max(rungs)] if rungs else "-",
            "y" if any(e.get("event") == "reveal" for e in events) else "n",
            ",".join(verdicts) or "-",
        )
    )


def main(_argv: list[str]) -> int:
    """Print the report for every session file."""
    folder = session_log.sessions_dir()
    paths = sorted(folder.glob("*.jsonl"))
    if not paths:
        print(f"no coach sessions yet in {folder}")
        return 0
    print(_line(HEADER))
    for path in paths:
        print(row(path))
    return 0
