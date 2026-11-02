"""Retired: kept as a no-op so old CI steps keep passing.

TODO*.md files are banned and tasks live in the todo app, so there is nothing
left to warn about. Existing `.github/workflows/md-naming.yml` steps still call
`python3 .utils/md_naming/stale.py ...`; this stub accepts and ignores any argv,
prints nothing and exits 0 until those steps are swept out of every repo.
"""

from __future__ import annotations


def main() -> int:
    """Do nothing, successfully."""
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
