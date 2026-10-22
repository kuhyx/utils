"""Result lines (``PASS|FAIL|SKIP AR-XXX-NN msg``) and the exit-code policy."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TextIO

EXIT_OK, EXIT_FAIL, EXIT_USAGE, EXIT_NETWORK = 0, 1, 2, 3


class Undeterminable(Exception):
    """A network-level failure (refused, timeout, deadline): no verdict."""


@dataclass
class Report:
    """Collects check lines and decides the exit code.

    Every in-scope item is required for kuhy's sites, so a FAIL of any
    strength (MUST/SHOULD/MAY) fails the run. SKIP never fails it.
    """

    out: TextIO = field(default_factory=lambda: sys.stdout)
    fails: int = 0
    undetermined: int = 0

    def emit(self, status: str, ar_id: str, msg: str) -> None:
        """Print one result line."""
        if status == "FAIL":
            self.fails += 1
        print(f"{status} {ar_id} {msg}", file=self.out, flush=True)

    def ok(self, ar_id: str, msg: str) -> None:
        """Emit PASS."""
        self.emit("PASS", ar_id, msg)

    def fail(self, ar_id: str, msg: str) -> None:
        """Emit FAIL."""
        self.emit("FAIL", ar_id, msg)

    def skip(self, ar_id: str, msg: str) -> None:
        """Emit SKIP."""
        self.emit("SKIP", ar_id, msg)

    def verdict(self, ar_id: str, problems: list[str], pass_msg: str) -> bool:
        """FAIL with the problems joined, or PASS with ``pass_msg``."""
        if problems:
            self.fail(ar_id, "; ".join(problems))
            return False
        self.ok(ar_id, pass_msg)
        return True

    def guard(self, ar_id: str, fn: Callable[[], object]) -> None:
        """Run a check; a network failure becomes an undeterminable SKIP."""
        try:
            fn()
        except Undeterminable as exc:
            self.undetermined += 1
            self.skip(ar_id, f"undeterminable (network): {exc}")

    def exit_code(self) -> int:
        """0 all pass, 1 any fail, 3 nothing failed but something undeterminable."""
        if self.fails:
            return EXIT_FAIL
        return EXIT_NETWORK if self.undetermined else EXIT_OK


def summarize(items: list[str], limit: int = 4) -> str:
    """Join up to ``limit`` items and note how many more there were."""
    head = ", ".join(items[:limit])
    return head + (f" (+{len(items) - limit} more)" if len(items) > limit else "")
