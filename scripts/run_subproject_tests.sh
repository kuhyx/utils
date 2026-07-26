#!/bin/bash

# ============================================================================
# Run one subproject's test suite from that subproject's directory.
#
# Every subproject here keeps its own pyproject.toml, and its pytest config
# (testpaths, --cov=..., coverage source) is relative to that directory --
# but pre-commit always runs hooks from the monorepo's git root. This wrapper
# supplies the missing `cd`, and fails loudly if the subproject is gone,
# rather than silently testing nothing.
#
# Usage: scripts/run_subproject_tests.sh <subproject> [pytest args...]
# ============================================================================

set -euo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SCRIPT_NAME="$(basename "$0")"

usage() {
    echo "Usage: $SCRIPT_NAME <subproject> [pytest args...]"
    echo "  <subproject>  directory under $REPO_ROOT holding a pyproject.toml"
    exit 1
}

main() {
    if [[ $# -lt 1 ]]; then
        usage
    fi
    local subproject="$1"
    shift
    local project_dir="$REPO_ROOT/$subproject"

    if [[ ! -f "$project_dir/pyproject.toml" ]]; then
        echo "Error: no $subproject/pyproject.toml under $REPO_ROOT" >&2
        echo "       (was the subproject renamed or removed?)" >&2
        exit 1
    fi

    cd "$project_dir"
    exec python -m pytest "$@"
}

main "$@"
