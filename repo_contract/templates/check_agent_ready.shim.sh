#!/bin/bash

# ============================================================================
# Fail if this repo's website fails the AgentReady checker.
#
# Thin delegate to the shared gate in ~/src/utils, which owns the config
# parsing, the build step and the checker call. Copy this file to
# scripts/check_agent_ready.sh in a repo; never copy the shared gate itself.
# ============================================================================

set -euo pipefail

readonly SHARED_GATE="${UTILS_ROOT:-$HOME/src/utils}/scripts/check_agent_ready.sh"

main() {
    if [[ ! -x "$SHARED_GATE" ]]; then
        echo "Error: shared agent-ready gate not found at $SHARED_GATE" >&2
        echo "       Clone github.com/kuhyx/utils to ~/src/utils, or set" >&2
        echo "       UTILS_ROOT to where it lives." >&2
        exit 1
    fi

    exec bash "$SHARED_GATE" "$@"
}

main "$@"
