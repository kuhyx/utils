#!/bin/bash

# ============================================================================
# Fail if any dependency in the commit is behind its ecosystem's newest stable.
#
# Thin delegate to the shared gate in ~/utils, which owns the registry
# adapters, the pre-release rules and the allowlist semantics. Copying that
# logic here is what lets one repo's idea of "current" drift from every other
# repo's -- so this script only locates the shared checker and forwards its
# arguments.
#
# Usage:
#   scripts/check_dependency_freshness.sh <file> [<file> ...]   # pre-commit
#   scripts/check_dependency_freshness.sh --all --strict        # CI
#
# Exit: 0 current | 1 behind | 2 allowlist wrong | 3 undeterminable (offline)
# ============================================================================

set -euo pipefail

readonly SHARED_GATE="${UTILS_ROOT:-$HOME/utils}/scripts/check_dependency_freshness.sh"

main() {
    if [[ ! -x "$SHARED_GATE" ]]; then
        echo "Error: shared dependency-freshness gate not found at $SHARED_GATE" >&2
        echo "       Clone github.com/kuhyx/utils to ~/utils, or set" >&2
        echo "       UTILS_ROOT to where it lives." >&2
        exit 1
    fi

    exec bash "$SHARED_GATE" "$@"
}

main "$@"
