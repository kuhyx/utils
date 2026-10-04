#!/bin/bash

# ============================================================================
# Fail if this repo breaks the shared repo contract.
#
# Thin delegate to the shared gate in ~/src/utils, which owns the contract
# text. Copy this file to scripts/check_repo_contract.sh in a repo; never copy
# the shared gate itself, or the shim would exec itself forever.
# ============================================================================

set -euo pipefail

readonly SHARED_GATE="${UTILS_ROOT:-$HOME/src/utils}/scripts/check_repo_contract.sh"

main() {
    if [[ ! -x "$SHARED_GATE" ]]; then
        echo "Error: shared repo-contract gate not found at $SHARED_GATE" >&2
        echo "       Clone github.com/kuhyx/utils to ~/src/utils, or set" >&2
        echo "       UTILS_ROOT to where it lives." >&2
        exit 1
    fi

    exec bash "$SHARED_GATE" "$@"
}

main "$@"
