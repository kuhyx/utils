#!/bin/bash

# ============================================================================
# Fail if the current repo breaks the repo contract: CLAUDE.md `## Commands`
# with run / test / test-changed / lint / coverage / coverage-gaps entries and
# a quiet scripts/test_changed.sh. See repo_contract/README.md.
#
# This is the REAL gate. Per-repo scripts/check_repo_contract.sh files are thin
# shims that exec this one -- do not overwrite this file with a shim.
#
# Usage: scripts/check_repo_contract.sh [--repo PATH]   # default: cwd
# Exit: 0 pass, 1 violations, 2 not a repo / unreadable.
# ============================================================================

set -euo pipefail

UTILS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly UTILS_ROOT

main() {
    PYTHONPATH="$UTILS_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        python3 "$UTILS_ROOT/repo_contract/check.py" "$@"
}

main "$@"
