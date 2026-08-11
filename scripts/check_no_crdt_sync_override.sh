#!/bin/bash

# ============================================================================
# Fail if a pubspec still overrides crdt_sync with a local path.
#
# The apps depend on crdt_sync as a *git dependency pinned to a tag*, so what
# CI builds is whatever that tag points at. A `dependency_overrides:` entry
# pointing at ~/utils/crdt_sync_dart is invaluable while developing an unreleased
# library change -- and catastrophic if it survives the commit: local tests go
# green against code CI has never seen, and the failure is silent in both
# directions.
#
# A comment in the pubspec asking someone to remember is deployment hygiene,
# not a fix. This is the gate.
#
# Usage: check_no_crdt_sync_override.sh [pubspec.yaml ...]
#   With no arguments, checks ./pubspec.yaml.
# ============================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_NAME

usage() {
    echo "Usage: $SCRIPT_NAME [pubspec.yaml ...]"
    echo "  Fails when a pubspec overrides crdt_sync with a local path."
    exit 0
}

# Returns 0 (found) when the file has a crdt_sync entry under
# dependency_overrides. Deliberately a small state machine rather than a grep:
# `path:` appears under plenty of other keys, and a false positive here blocks
# a legitimate commit.
has_override() {
    local file="$1"
    awk '
        # Track indent depth explicitly. An earlier version used an awk
        # interval expression ({1,4}) to spot a sibling key, which plain awk
        # does not enable by default -- so the check silently never fired and
        # reported every file clean. A safety check that fails open is worse
        # than none, so this version is written to be obvious instead of terse.
        function indent(line,   n) {
            n = match(line, /[^ ]/)
            return (n == 0) ? 0 : n - 1
        }
        /^[[:space:]]*#/ { next }            # comments
        /^[[:space:]]*$/ { next }            # blank lines
        /^dependency_overrides:[[:space:]]*$/ { in_overrides = 1; next }
        /^[^[:space:]]/  { in_overrides = 0; in_crdt = 0; next }
        in_overrides {
            if ($0 ~ /^[[:space:]]+crdt_sync:[[:space:]]*$/) {
                in_crdt = 1
                crdt_indent = indent($0)
                next
            }
            # Any key at or above crdt_sync{s} own indent ends its block.
            if (in_crdt && indent($0) <= crdt_indent) { in_crdt = 0 }
            if (in_crdt && $0 ~ /^[[:space:]]+path:/) { found = 1 }
        }
        END { exit(found ? 0 : 1) }
    ' "$file"
}

main() {
    local -a files=("$@")
    if [[ ${#files[@]} -eq 0 ]]; then
        files=("pubspec.yaml")
    fi

    local failed=0
    for file in "${files[@]}"; do
        [[ -f "$file" ]] || continue
        if has_override "$file"; then
            echo "Error: $file still has a local crdt_sync dependency_override." >&2
            echo "       Remove it and bump the git 'ref:' to the released tag" >&2
            echo "       before committing, or CI will build different code." >&2
            failed=1
        fi
    done
    return "$failed"
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
fi

main "$@"
