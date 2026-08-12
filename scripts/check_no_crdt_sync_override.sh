#!/bin/bash

# ============================================================================
# Fail if a pubspec still overrides a git-dependency utils package with a
# local path.
#
# The apps depend on packages in this repo (crdt_sync, sync_settings_ui) as
# a *git dependency pinned to a tag*, so what CI builds is whatever that tag
# points at. A `dependency_overrides:` entry pointing at a local checkout is
# invaluable while developing an unreleased library change -- and
# catastrophic if it survives the commit: local tests go green against code
# CI has never seen, and the failure is silent in both directions.
#
# A comment in the pubspec asking someone to remember is deployment hygiene,
# not a fix. This is the gate.
#
# Usage: check_no_crdt_sync_override.sh [-p package_name] [pubspec.yaml ...]
#   -p package_name  Check this package instead of the default set. May be
#                     repeated. Default: crdt_sync sync_settings_ui.
#   With no pubspec.yaml arguments, checks ./pubspec.yaml.
# ============================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_NAME
DEFAULT_PACKAGES=(crdt_sync sync_settings_ui)

usage() {
    echo "Usage: $SCRIPT_NAME [-p package_name ...] [pubspec.yaml ...]"
    echo "  Fails when a pubspec overrides a utils git dependency with a local path."
    echo "  Default packages checked: ${DEFAULT_PACKAGES[*]}"
    exit 0
}

# Returns 0 (found) when the file has a $package entry under
# dependency_overrides. Deliberately a small state machine rather than a grep:
# `path:` appears under plenty of other keys, and a false positive here blocks
# a legitimate commit.
has_override() {
    local file="$1" package="$2"
    awk -v package="$package" '
        # Track indent depth explicitly. An earlier version used an awk
        # interval expression ({1,4}) to spot a sibling key, which plain awk
        # does not enable by default -- so the check silently never fired and
        # reported every file clean. A safety check that fails open is worse
        # than none, so this version is written to be obvious instead of terse.
        function indent(line,   n) {
            n = match(line, /[^ ]/)
            return (n == 0) ? 0 : n - 1
        }
        /^[[:space:]]*#/ { next }            # comments
        /^[[:space:]]*$/ { next }            # blank lines
        /^dependency_overrides:[[:space:]]*$/ { in_overrides = 1; next }
        /^[^[:space:]]/  { in_overrides = 0; in_pkg = 0; next }
        in_overrides {
            if ($0 ~ ("^[[:space:]]+" package ":[[:space:]]*$")) {
                in_pkg = 1
                pkg_indent = indent($0)
                next
            }
            # Any key at or above the package own indent ends its block.
            if (in_pkg && indent($0) <= pkg_indent) { in_pkg = 0 }
            if (in_pkg && $0 ~ /^[[:space:]]+path:/) { found = 1 }
        }
        END { exit(found ? 0 : 1) }
    ' "$file"
}

main() {
    local -a packages=() files=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                usage
                ;;
            -p)
                packages+=("$2")
                shift 2
                ;;
            *)
                files+=("$1")
                shift
                ;;
        esac
    done

    if [[ ${#packages[@]} -eq 0 ]]; then
        packages=("${DEFAULT_PACKAGES[@]}")
    fi
    if [[ ${#files[@]} -eq 0 ]]; then
        files=("pubspec.yaml")
    fi

    local failed=0
    for file in "${files[@]}"; do
        [[ -f "$file" ]] || continue
        for package in "${packages[@]}"; do
            if has_override "$file" "$package"; then
                echo "Error: $file still has a local $package dependency_override." >&2
                echo "       Remove it and bump the git 'ref:' to the released tag" >&2
                echo "       before committing, or CI will build different code." >&2
                failed=1
            fi
        done
    done
    return "$failed"
}

main "$@"
