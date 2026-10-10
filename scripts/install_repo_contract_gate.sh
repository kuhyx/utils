#!/bin/bash

# ============================================================================
# Install the repo-contract gate into a repo and bootstrap its CLAUDE.md
# `## Commands` section plus scripts/test_changed.sh.
#
# Run this on EVERY new repo, right after `git init`. Idempotent. Pieces:
# scripts/check_repo_contract.sh shim, pre-commit hook, CI workflow (skipped
# when the repo has .dep-freshness-no-workflow), Commands section.
#
# Usage: scripts/install_repo_contract_gate.sh <repo> [--check] [--no-bootstrap]
# Exit: 0 contract satisfied | 1 violations left (e.g. <FILL IN>) | 2 not a git repo
# ============================================================================

set -euo pipefail

UTILS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly UTILS_ROOT

main() {
    if [[ $# -lt 1 ]]; then
        echo "Usage: $(basename "$0") <repo> [--check] [--no-bootstrap]" >&2
        exit 1
    fi
    PYTHONPATH="$UTILS_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        python3 -m repo_contract.install "$@"
}

main "$@"
