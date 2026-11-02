#!/bin/bash

# ============================================================================
# Fail if any markdown file breaks the shared naming convention.
#
# Three namespaces -- README.md, CLAUDE*.md, DOCS*.md. TODO*.md is banned:
# tasks live in the todo app (MCP add_task, or todo_note.dart --repo).
#
# This is the REAL gate. Per-repo scripts/check_md_naming.sh files are thin
# shims that exec this one -- do not overwrite this file with a shim, or every
# shim execs itself forever.
#
# The real check lives in Python (md_naming/check.py) so that the gate and any
# survey share one exemption list -- see rules/shell.instructions.md on never
# embedding another language's logic inline.
#
# Usage:
#   scripts/check_md_naming.sh <file> [<file> ...]   # pre-commit passes these
#   scripts/check_md_naming.sh --all                 # whole tree, from cwd
# ============================================================================

set -euo pipefail

UTILS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly UTILS_ROOT
readonly CHECKER="$UTILS_ROOT/md_naming/check.py"

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
