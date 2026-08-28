#!/bin/bash

# ============================================================================
# Install the dependency-freshness gate's three pieces into a repo.
#
# The gate is a delegate script + a pre-commit hook entry + a CI workflow, and
# every repo needs all three. Copying them by hand across ~16 repos is what
# produced four different ids for the 250-line cap, two of them independent
# reimplementations, so the copy lives here and the templates have one home
# (utils/dep_freshness/templates/).
#
# Idempotent: a second run reports "already current" and writes nothing.
#
# NOTE: never install the gate ahead of the upgrade. A repo that gets the gate
# while its dependencies are still stale is instantly and permanently red --
# gate and upgrade belong in the same commit.
#
# Usage:
#   scripts/install_dependency_freshness_gate.sh <repo> [--check] [--fvm]
#
# Options:
#   --check   report what a run would write, change nothing
#   --fvm     also pin the Flutter SDK in <repo>/.fvmrc (Dart repos only)
#
# Exit: 0 installed or already current | 1 bad usage / missing repo
# ============================================================================

set -euo pipefail

readonly UTILS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SCRIPT_NAME="$(basename "$0")"

REPO=""
CHECK=""
FVM=""

usage() {
    echo "Usage: $SCRIPT_NAME <repo> [--check] [--fvm]"
    echo "  --check   report what would be written, change nothing"
    echo "  --fvm     also write <repo>/.fvmrc pinning the Flutter SDK"
    exit 0
}

validate_requirements() {
    if [[ -z "$REPO" ]]; then
        echo "Error: a repository path is required" >&2
        exit 1
    fi
    if [[ ! -d "$REPO" ]]; then
        echo "Error: no such directory: $REPO" >&2
        exit 1
    fi
}

main() {
    validate_requirements
    PYTHONPATH="$UTILS_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        python3 -m dep_freshness.install_main "$REPO" $CHECK $FVM
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --check)
            CHECK="--check"
            shift
            ;;
        --fvm)
            FVM="--fvm"
            shift
            ;;
        -h|--help)
            usage
            ;;
        -*)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
        *)
            REPO="$1"
            shift
            ;;
    esac
done

main
