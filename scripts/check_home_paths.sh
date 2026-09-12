#!/bin/bash

# ============================================================================
# Fail if code builds a ~/<name> path that ~ is not allowed to contain.
#
# The 2026-09-11 reorganisation left ~ with eleven visible entries. Its
# reference rewriter matched *literal* /home/kuhy/<name> strings and a few
# uppercase forms, so lowercase segment-joined paths survived untouched --
# the todo desktop wrapper kept exporting to a dead ~/todo for a day while
# its MCP read ~/src/todo, and every backlog read in between came back
# stale. This gate matches the shape, not a list of old names, so it stays
# correct as repos come and go.
#
# The real check lives in Python (home_paths/check.py) so the gate and any
# survey share one rule set -- see rules/shell.instructions.md on never
# embedding another language's logic inline.
#
# Usage:
#   scripts/check_home_paths.sh <file> [<file> ...]   # pre-commit passes these
#   scripts/check_home_paths.sh --all [<root>]        # whole tree, default cwd
# ============================================================================

set -euo pipefail

readonly UTILS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly CHECKER="$UTILS_ROOT/home_paths/check.py"

main() {
    if [[ $# -eq 0 ]]; then
        echo "Usage: $(basename "$0") <file>... | --all [<root>]" >&2
        exit 1
    fi
    if [[ ! -f "$CHECKER" ]]; then
        echo "Error: checker not found at $CHECKER" >&2
        exit 1
    fi

    PYTHONPATH="$UTILS_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        python3 "$CHECKER" "$@"
}

main "$@"
