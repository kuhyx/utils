# Copyright (c) 2026 Krzysztof Rudnicki
"""Every on-disk and network location, resolved in one place.

Tests redirect :func:`resolve_paths` once; nothing else names a real path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MCP_URL = "http://127.0.0.1:8735/mcp"
# Port 9 (discard) refuses connections: a test that forgets to inject a client
# fails closed instead of reaching the live todo server.
DEAD_URL = "http://127.0.0.1:9/mcp"


@dataclass(frozen=True)
class Paths:
    """Where the inbox reads games, its token, its lock and its units."""

    data_root: Path
    token_file: Path
    lock_file: Path
    unit_dir: Path
    mcp_url: str

    @classmethod
    def under(cls, root: Path) -> Paths:
        """A throwaway layout below ``root`` that can never reach the live app."""
        return cls(
            data_root=root / "data",
            token_file=root / "token",
            lock_file=root / "state" / "lock",
            unit_dir=root / "units",
            mcp_url=DEAD_URL,
        )


def resolve_paths(given: Paths | None = None) -> Paths:
    """Return ``given`` or the real layout under the user's home."""
    if given is not None:
        return given
    home = Path.home()
    return Paths(
        data_root=home / "data",
        token_file=home / ".config" / "feedback-inbox" / "token",
        lock_file=home / ".local" / "share" / "feedback-inbox" / "lock",
        unit_dir=home / ".config" / "systemd" / "user",
        mcp_url=MCP_URL,
    )
