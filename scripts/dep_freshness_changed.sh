#!/bin/bash
# ============================================================================
# dep_freshness_changed.sh - run the dependency-freshness gate on the
# manifests THIS BRANCH changed, not on every manifest pre-commit hands over.
#
# Why: `pre-commit run --all-files` (the todoImplementer runner's check) passes
# every manifest in the monorepo, so one feature branch went red on 43 stale
# pins in 12 projects it never touched. Scoping to changed manifests makes the
# hook answer "did this change leave a stale pin?". The repo-wide question
# stays with CI (.github/workflows/dependency-freshness.yml: --all --strict).
#
# "Changed" = differs from the merge-base with $DEP_FRESHNESS_BASE (default
# main, then origin/main), working tree included, plus untracked files.
# A plain commit only passes staged files, which are all "changed", so normal
# commits behave exactly as before.
#
# Fails closed: no resolvable base, or a cwd that is not the repo root (so
# paths cannot be compared), forwards every file unfiltered.
#
# Usage: scripts/dep_freshness_changed.sh <file>...
# Env:   DEP_FRESHNESS_GATE  gate to call (default: check_dependency_freshness.sh
#                            next to this script); DEP_FRESHNESS_BASE (main)
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly GATE="${DEP_FRESHNESS_GATE:-$SCRIPT_DIR/check_dependency_freshness.sh}"
readonly BASE="${DEP_FRESHNESS_BASE:-main}"

# Print the merge-base with $BASE (or origin/$BASE); empty when neither exists.
merge_base() {
    local ref
    for ref in "$BASE" "origin/$BASE"; do
        if git rev-parse --verify --quiet "$ref^{commit}" >/dev/null; then
            git merge-base HEAD "$ref" 2>/dev/null && return
        fi
    done
}

# Print root-relative paths changed since $1, one per line.
changed_since() {
    git diff --name-only "$1"
    git ls-files --others --exclude-standard --full-name
}

main() {
    local base
    base="$(merge_base || true)"
    if [[ -z "$base" || -n "$(git rev-parse --show-prefix)" ]]; then
        exec bash "$GATE" "$@"
    fi

    local -A changed=()
    local path
    while IFS= read -r path; do
        changed["$path"]=1
    done < <(changed_since "$base")

    local -a keep=()
    for path in "$@"; do
        if [[ -n "${changed[$path]:-}" ]]; then
            keep+=("$path")
        fi
    done

    if [[ ${#keep[@]} -eq 0 ]]; then
        exit 0
    fi
    exec bash "$GATE" "${keep[@]}"
}

main "$@"
