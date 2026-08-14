#!/bin/bash

# ============================================================================
# Fail if any file exceeds the shared 250-line cap.
#
# A file that cannot be read in one piece forces re-reads and partial edits,
# which is the largest avoidable cost in an LLM-assisted workflow. The cap
# applies to code AND prose; generated files, markup and data are exempt.
#
# The real check lives in Python (file_length/check.py) so that the gate and
# the survey share one exemption list -- see rules/shell.instructions.md on
# never embedding another language's logic inline.
#
# Usage:
#   scripts/check_file_length.sh <file> [<file> ...]   # pre-commit passes these
#   scripts/check_file_length.sh --all                 # whole tree, from cwd
# ============================================================================

set -euo pipefail

readonly UTILS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly CHECKER="$UTILS_ROOT/file_length/check.py"

main() {
    if [[ $# -eq 0 ]]; then
        echo "Usage: $(basename "$0") <file>... | --all" >&2
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
