"""Format-neutral data model shared by every parser and renderer."""

from __future__ import annotations

from dataclasses import dataclass, field


class ReportError(Exception):
    """The input is unreadable, unrecognised or malformed (exit code 2)."""


@dataclass
class FileAccumulator:
    """Mutable per-file collector that merges repeated records for one path.

    Reports may list a file more than once (lcov re-runs, Cobertura inner
    classes). A line or branch counts as covered if ANY record covered it.
    """

    lines: dict[int, bool] = field(default_factory=dict)
    branches: dict[tuple[int, int, int], bool] = field(default_factory=dict)

    def add_line(self, line: int, covered: bool) -> None:
        """Record a line, OR-merging with earlier records of the same line."""
        self.lines[line] = self.lines.get(line, False) or covered

    def add_branch(self, line: int, block: int, index: int, covered: bool) -> None:
        """Record one branch outcome, OR-merging on (line, block, index)."""
        key = (line, block, index)
        self.branches[key] = self.branches.get(key, False) or covered


@dataclass(frozen=True)
class FileGap:
    """Coverage state of one source file."""

    path: str
    total_lines: int
    missed_lines: tuple[int, ...]
    total_branches: int
    missed_branch_lines: tuple[int, ...]
    missed_branches: int

    @property
    def missed(self) -> int:
        """Missed lines plus missed branches: the sort key."""
        return len(self.missed_lines) + self.missed_branches

    @property
    def percent(self) -> float:
        """Percent covered over lines and branches combined (100 if empty)."""
        total = self.total_lines + self.total_branches
        if total == 0:
            return 100.0
        return 100.0 * (total - self.missed) / total


def build_gap(path: str, acc: FileAccumulator) -> FileGap:
    """Freeze an accumulator into a FileGap."""
    missed_lines = tuple(sorted(n for n, ok in acc.lines.items() if not ok))
    missed_br = [key for key, ok in acc.branches.items() if not ok]
    return FileGap(
        path=path,
        total_lines=len(acc.lines),
        missed_lines=missed_lines,
        total_branches=len(acc.branches),
        missed_branch_lines=tuple(sorted({key[0] for key in missed_br})),
        missed_branches=len(missed_br),
    )
