#!/bin/bash

# ============================================================================
# Fail if the current repo's website fails the AgentReady checker.
#
# Reads [agent_ready] from repo-contract.toml (dist = build dir, url = live
# site, skip = not a website), runs the build, then agent_ready/check.sh.
# See repo_contract/web.py and agent_ready/README.md.
#
# This is the REAL gate. Per-repo scripts/check_agent_ready.sh files are thin
# shims that exec this one -- do not overwrite this file with a shim.
#
# Usage: scripts/check_agent_ready.sh [--repo PATH] [--strict] [--install]
# Exit: 0 pass | 1 FAIL | 2 bad config | 3 undeterminable (--strict only)
# ============================================================================

set -euo pipefail

UTILS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly UTILS_ROOT

main() {
    PYTHONPATH="$UTILS_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        python3 "$UTILS_ROOT/repo_contract/agent_ready_gate.py" "$@"
}

main "$@"
