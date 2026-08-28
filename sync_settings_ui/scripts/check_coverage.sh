#!/bin/bash

# ============================================================================
# Fail if lcov line coverage drops below a threshold.
#
# Thin delegate to the shared gate in ~/utils/scripts, which owns the parsing
# and the threshold comparison. This file used to be a byte-identical copy of
# that logic; three such copies existed, which is how one package's idea of
# "covered" drifts from every other package's.
#
# Usage: check_coverage.sh <lcov.info> <min_percent>
# ============================================================================

set -euo pipefail

# Repo-relative, resolved from this script's own location: an absolute
# /home/... path exits 127 on an Actions runner.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly SHARED_GATE="${SCRIPT_DIR}/../../scripts/check_coverage.sh"

main() {
    if [[ ! -f "$SHARED_GATE" ]]; then
        echo "Error: shared coverage gate not found at $SHARED_GATE" >&2
        echo "       It lives in the utils repo at scripts/check_coverage.sh." >&2
        exit 1
    fi

    exec bash "$SHARED_GATE" "$@"
}

main "$@"
