"""Recognising a home-relative path, however it is spelled.

The 2026-09-11 ``~`` reorganisation rewrote references by matching *literal*
``/home/kuhy/<name>`` strings. Every path assembled at run time from
segments was invisible to it, which is how the todo desktop wrapper went on
exporting to a dead ``~/todo`` for a day while its MCP read ``~/src/todo``.

So this module does not look for the old paths. It looks for the *shape* --
"home, then a first segment" -- and lets :mod:`check` judge the segment
against the eleven names ``~`` is allowed to contain. A construction that
resolves to any other first segment cannot be correct, whether or not it
happens to name a directory that moved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Identifiers that plausibly hold the home directory. Deliberately narrow:
# `root`, `base` and `dir` hold anything at all and would swamp the gate.
HOME_VARS = r"(?:home|homeDir|home_dir|HOME|userHome|user_home|homedir)"

# A first path segment: visible (a leading dot is a dotfile, never our
# business) and not a variable/placeholder, which we cannot resolve.
# Must not end on a dot: `~/utils.` in English prose is a sentence, not a path.
SEGMENT = r"(?P<seg>[A-Za-z0-9][\w+-]*(?:\.[\w+-]+)*)"


@dataclass(frozen=True)
class Pattern:
    """One way of spelling ``<home>/<segment>``."""

    name: str
    regex: re.Pattern[str]


def _p(name: str, pattern: str) -> Pattern:
    return Pattern(name, re.compile(pattern))


PATTERNS: tuple[Pattern, ...] = (
    # Python: Path.home() / "seg"   and   Path.home().joinpath("seg")
    _p("py-pathlib", rf"Path\.home\(\)\s*(?:/|\.joinpath\()\s*[\"']{SEGMENT}"),
    # Python: os.path.join(os.environ["HOME"], "seg") / expanduser("~/seg")
    _p(
        "py-environ",
        rf"os\.environ(?:\.get)?[\[(]\s*[\"']HOME[\"']\s*[\])](?:\s*,\s*[\"']|\s*\+\s*[\"']/?){SEGMENT}",
    ),
    _p("py-expanduser", rf"expanduser\(\s*[\"']~/{SEGMENT}"),
    # Dart/JS/Go: join(home, 'seg', ...) -- p.join, path.join, filepath.Join
    _p(
        "join-call",
        rf"\b(?:[pP]\.)?(?:path\.|filepath\.)?[jJ]oin\(\s*{HOME_VARS}\s*,\s*[\"']{SEGMENT}",
    ),
    # JS/TS: path.join(os.homedir(), 'seg')
    _p("js-homedir", rf"homedir\(\)\s*,\s*[\"']{SEGMENT}"),
    # Interpolation: "$home/seg", "${home}/seg", f"{home}/seg"
    _p("interp", rf"[\"'`]?\$\{{?{HOME_VARS}\}}?/{SEGMENT}"),
    _p("fstring", rf"\{{\s*{HOME_VARS}\s*\}}/{SEGMENT}"),
)


def first_segments(line: str) -> list[tuple[str, str]]:
    """Every ``(pattern_name, first_segment)`` this line constructs."""
    out: list[tuple[str, str]] = []
    for pattern in PATTERNS:
        for match in pattern.regex.finditer(line):
            out.append((pattern.name, match.group("seg")))
    return out
