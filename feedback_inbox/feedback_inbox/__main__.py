# Copyright (c) 2026 Krzysztof Rudnicki
"""``python -m feedback_inbox``."""

from __future__ import annotations

from feedback_inbox._cli import main


def run() -> int:
    """Run the CLI on ``sys.argv``."""
    return main()


if __name__ == "__main__":
    raise SystemExit(run())
