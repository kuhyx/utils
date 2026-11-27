#!/bin/bash
# ============================================================================
# One-shot devstats run: installs python3/git when missing (pacman), runs
# `python -m devstats compare` over ~/src (or the given --root), prints the
# tables, writes ~/data/devstats/report.html and opens it unless --no-open.
# Works from any cwd: the repo root is found from this script's own path.
# Usage: run.sh [--no-open] [compare flags...]   (run.sh --help lists them)
# Exit: devstats' own code (2 = no repos), 3 = setup failed.
# ============================================================================

set -euo pipefail

SELF="$(realpath "${BASH_SOURCE[0]}")"
readonly SELF
REPO_ROOT="$(dirname "$(dirname "$SELF")")"
readonly REPO_ROOT
readonly REPORT="$HOME/data/devstats/report.html"
readonly CAPPED="$HOME/.claude/scripts/capped.sh"
readonly EXIT_SETUP=3

die() {
    echo "devstats: $*" >&2
    exit "$EXIT_SETUP"
}

# Install every missing tool first, then re-check, so one run installs both.
ensure_tools() {
    local pair tool pkg
    for pair in python3:python git:git; do
        tool="${pair%%:*}" pkg="${pair#*:}"
        if ! command -v "$tool" >/dev/null; then
            sudo pacman -S --needed "$pkg" || die "pacman could not install $pkg"
        fi
    done
    for tool in python3 git; do
        command -v "$tool" >/dev/null || die "$tool still missing after install"
    done
}

# devstats needs datetime.UTC (3.11+); it has no third-party dependencies.
check_python() {
    local ver major minor
    ver="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    major="${ver%%.*}" minor="${ver#*.}"
    if ((major < 3 || (major == 3 && minor < 11))); then
        die "python3 >= 3.11 required, found $ver"
    fi
}

# Capped (2 GiB, 10 % CPU, idle IO) when kuhy's capped.sh exists, plain otherwise.
run_devstats() {
    local cmd=(env "PYTHONPATH=$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -m devstats compare "$@")
    if [[ -x "$CAPPED" ]]; then
        "$CAPPED" "${cmd[@]}"
    else
        "${cmd[@]}"
    fi
}

usage() {
    echo "usage: run.sh [--no-open] [compare flags...]"
    echo "  --no-open  write $REPORT but do not open it"
    echo
    run_devstats --help
}

main() {
    local open=1 help=0 args=() arg rc=0
    for arg in "$@"; do
        case "$arg" in
            --no-open) open=0 ;;
            -h | --help) help=1 ;;
            *) args+=("$arg") ;;
        esac
    done
    ensure_tools
    check_python
    if ((help)); then
        usage
        return 0
    fi
    if ((open)) && ! command -v xdg-open >/dev/null; then
        die "xdg-open missing: install xdg-utils or pass --no-open"
    fi
    run_devstats "${args[@]}" --html "$REPORT" || rc=$?
    if ((rc == 0 && open)); then
        setsid -f xdg-open "$REPORT" >/dev/null 2>&1
    fi
    return "$rc"
}

main "$@"; exit $?
