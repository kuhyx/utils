"""Every on-disk location the hooks use, overridable for tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass
class Paths:
    """Config, state and lookup locations used by the todo hooks."""

    token_file: Path
    trust_file: Path
    report_file: Path
    src_root: Path
    capped: Path | None

    @classmethod
    def default(cls, env: Mapping[str, str], home: Path | None = None) -> Paths:
        """Resolve defaults under `home`; ``TODO_*`` env vars override each."""
        base = home if home is not None else Path.home()
        capped = base / ".claude" / "scripts" / "capped.sh"
        return cls(
            token_file=Path(
                env.get("TODO_MCP_TOKEN_FILE")
                or base / ".config" / "todo-mcp" / "client-token"
            ),
            trust_file=Path(
                env.get("TODO_HOOKS_TRUST_FILE")
                or base / ".config" / "todo-hooks" / "trusted-checks"
            ),
            report_file=Path(
                env.get("TODO_HOOKS_REPORT")
                or base / ".local" / "state" / "todo-drift" / "report.txt"
            ),
            src_root=Path(env.get("TODO_HOOKS_SRC_ROOT") or base / "src"),
            capped=capped if capped.is_file() else None,
        )
