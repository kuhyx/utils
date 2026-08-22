"""Static checks that the recovery loop *cannot* weaken the lock.

Split from ``test_recovery.py`` (250-line cap). These read the source with
``ast`` rather than running anything: monotonicity is enforced by which calls
a module is allowed to contain at all, so the check belongs at the source
level where no amount of mocking can fake it.
"""

from __future__ import annotations

import ast
from pathlib import Path

WEAKENING_CALLS = frozenset(
    {"grab_release", "restore_vt_switching", "close", "destroy", "quit", "withdraw"}
)
SOURCE_ROOT = Path(__file__).resolve().parent.parent


def symbols(module: str) -> set[str]:
    """Every attribute and name referenced in a module's source."""
    tree = ast.parse((SOURCE_ROOT / module).read_text(encoding="utf-8"))
    return {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
    }


class TestStaticInvariant:
    """The separation that makes monotonicity mechanical rather than hoped-for."""

    def test_recovery_contains_no_weakening_call(self) -> None:
        """_recovery.py must not be able to release, restore or destroy."""
        assert symbols("_recovery.py") & WEAKENING_CALLS == set()

    def test_recovery_may_still_strengthen(self) -> None:
        """The asymmetry is the point: strengthening calls ARE present."""
        found = symbols("_recovery.py")
        assert "disable_vt_switching" in found
        assert "grab_set_global" in found

    def test_surfaces_never_touches_grab_or_vt(self) -> None:
        """Window ownership and lock strength stay separate concerns."""
        banned = {"grab_release", "grab_set", "grab_set_global", "restore_vt_switching"}
        assert symbols("_surfaces.py") & banned == set()

    def test_detect_thread_never_touches_tk(self) -> None:
        """Tk is not thread-safe; the RandR thread may only queue."""
        source = (SOURCE_ROOT / "_detect.py").read_text(encoding="utf-8")
        loop_body = source.split("def _loop(")[1].split("def ")[0]
        assert "self._sink.put" in loop_body
        for forbidden in ("geometry(", "deiconify(", "lift(", "grab_"):
            assert forbidden not in loop_body
