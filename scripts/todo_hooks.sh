#!/bin/bash

# ============================================================================
# Run one todo_hooks subcommand (closer | sweep | trust | import-pr) from this
# utils checkout. This is the entry the .pre-commit-hooks.yaml hooks and the
# todo-drift systemd unit call, so a consuming repo needs no install step.
#
# Usage: scripts/todo_hooks.sh <subcommand> [args...]
# ============================================================================

set -euo pipefail

UTILS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly UTILS_ROOT

PYTHONPATH="$UTILS_ROOT${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m todo_hooks "$@"
