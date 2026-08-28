#!/bin/bash

# ============================================================================
# Fail if lcov line coverage drops below a threshold.
#
# THE shared coverage gate for every package in this repo. Three byte-identical
# copies of this file used to live under design_system/, github_device_auth/
# and sync_settings_ui/scripts/ -- each claiming in its own header to exist for
# one particular package. Those are now thin delegates to this file, for the
# same reason check_file_length.sh is shared: a per-package copy is how one
# package's idea of "covered" drifts from every other package's.
#
# Note for pure-Dart packages: `dart test --coverage` writes raw VM JSON, NOT
# lcov. Run coverage:format_coverage before this gate, or it will happily pass
# against a stale lcov.info from a previous run. crdt_sync_dart really did sit
# at 96% for three weeks that way while believing it was at 100%.
#
# Usage: check_coverage.sh <lcov.info> <min_percent>
# ============================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_NAME

usage() {
    echo "Usage: $SCRIPT_NAME <lcov.info> <min_percent>"
    echo "  Fails when line coverage in lcov.info is below min_percent."
    exit 0
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
fi

if [[ $# -ne 2 ]]; then
    usage
fi

lcov_file="$1"
min_percent="$2"

if [[ ! -f "$lcov_file" ]]; then
    echo "Error: $lcov_file not found. Run 'flutter test --coverage' first." >&2
    exit 1
fi

# Sum LH (lines hit) and LF (lines found) across every SF (source file)
# block rather than trusting a single top-level total -- lcov.info has no
# such total line, only per-file LH/LF pairs.
read -r hit found <<< "$(awk '
    /^LH:/ { hit += substr($0, 4) }
    /^LF:/ { found += substr($0, 4) }
    END { print hit, found }
' "$lcov_file")"

if [[ "$found" -eq 0 ]]; then
    echo "Error: $lcov_file reports zero coverable lines." >&2
    exit 1
fi

percent=$(awk -v h="$hit" -v f="$found" 'BEGIN { printf "%.2f", (h / f) * 100 }')
meets_threshold=$(awk -v p="$percent" -v m="$min_percent" 'BEGIN { print (p + 0 >= m + 0) ? 1 : 0 }')

echo "Line coverage: $hit/$found ($percent%), threshold: $min_percent%"

if [[ "$meets_threshold" -ne 1 ]]; then
    echo "Error: coverage $percent% is below the required $min_percent%." >&2
    exit 1
fi
