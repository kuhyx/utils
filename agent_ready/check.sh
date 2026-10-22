#!/bin/bash
# Thin wrapper: run the AgentReady checker from any cwd.
#   check.sh dist <build-dir> [--act]
#   check.sh url <base-url> [--act]
# Exit codes: 0 all pass, 1 any FAIL, 2 usage error, 3 network undeterminable.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly HERE
PYTHONPATH="$(dirname "$HERE")${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m agent_ready.check "$@"
