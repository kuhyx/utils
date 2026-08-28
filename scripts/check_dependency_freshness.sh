#!/bin/bash

# ============================================================================
# Fail if any dependency is behind its ecosystem's newest stable release.
#
# "Are we on the newest version?" is only mechanically answerable when the
# manifest states an exact version, so this gate checks two things at once:
# that every dependency is exact-pinned, and that the pin equals latest stable.
#
# The real check lives in Python (dep_freshness/check.py) so the pre-commit
# hook, the CI workflow and the SessionStart hook read one implementation --
# see rules/shell.instructions.md on never embedding another language's logic
# inline, and the four-way fork of the 250-line cap on why delegation matters.
#
# Usage:
#   scripts/check_dependency_freshness.sh <file> [<file> ...]   # pre-commit
#   scripts/check_dependency_freshness.sh --all --strict        # CI
#
# Exit: 0 current | 1 behind | 2 allowlist wrong | 3 undeterminable (offline)
# ============================================================================

set -euo pipefail

readonly UTILS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly CHECKER="$UTILS_ROOT/dep_freshness/check.py"

main() {
    if [[ $# -eq 0 ]]; then
        echo "Usage: $(basename "$0") <file>... | --all [--strict]" >&2
        exit 1
    fi
    if [[ ! -f "$CHECKER" ]]; then
        echo "Error: checker not found at $CHECKER" >&2
        echo "Clone kuhyx/utils next to this repo, or set UTILS_ROOT." >&2
        exit 1
    fi

    PYTHONPATH="$UTILS_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        python3 -m dep_freshness "$@"
}

main "$@"
