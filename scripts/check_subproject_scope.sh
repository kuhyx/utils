#!/bin/bash

# ============================================================================
# Fail if a subproject's pre-commit config is scoped to a directory that has
# moved or vanished.
#
# Each subproject config carries `files: ^<subproject>/`. If the directory is
# renamed, that regex matches nothing and EVERY hook in the config reports
# "no files to check" -- green CI with no linting at all. This hook runs with
# always_run, so the top-level filter cannot skip it, and turns that silent
# pass into a loud failure.
#
# Usage: scripts/check_subproject_scope.sh <subproject>
# ============================================================================

set -euo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

main() {
    if [[ $# -ne 1 ]]; then
        echo "Usage: $(basename "$0") <subproject>" >&2
        exit 1
    fi
    local subproject="$1"
    local config="$REPO_ROOT/$subproject/.pre-commit-config.yaml"

    if [[ ! -f "$config" ]]; then
        echo "Error: $subproject/.pre-commit-config.yaml is missing." >&2
        echo "       Every hook scoped to '^$subproject/' would silently pass." >&2
        exit 1
    fi
    if ! grep -qx "files: \^$subproject/" "$config"; then
        echo "Error: $config does not scope itself to '^$subproject/'." >&2
        echo "       Hooks would run over the whole monorepo, or over nothing." >&2
        exit 1
    fi
}

main "$@"
