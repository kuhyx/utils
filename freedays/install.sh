#!/bin/bash

# ============================================================================
# Install the freedays CLI and its sync timer for the current user.
#
# freedays gets its OWN venv rather than borrowing an app's. The pool is
# shared by five apps, so binding the command that manages it to whichever
# app venv happened to be active would make "is freedays installed?" depend
# on something unrelated -- and uninstalling that app would take the CLI with
# it. This is idempotent: rerun it after any change.
# ============================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UTILS_DIR="$(dirname "$REPO_DIR")"
readonly SCRIPT_NAME REPO_DIR UTILS_DIR
readonly STATE_DIR="${HOME}/.local/share/freedays"
readonly VENV_DIR="${STATE_DIR}/venv"
readonly BIN_DIR="${HOME}/.local/bin"
readonly UNIT_DIR="${HOME}/.config/systemd/user"
readonly SYSTEM_PYTHON="/usr/bin/python3"

log() { printf 'install: %s\n' "$1" >&2; }
fail() { printf 'install: FAILED -- %s\n' "$1" >&2; exit 1; }

usage() {
    echo "Usage: $SCRIPT_NAME [--no-timer]"
    echo "  --no-timer  install the CLI only; do not enable the sync timer"
    exit 0
}

INSTALL_TIMER=1

build_venv() {
    log "building the freedays venv at $VENV_DIR"
    mkdir -p "$STATE_DIR"
    if [[ ! -x "$VENV_DIR/bin/python" ]]; then
        "$SYSTEM_PYTHON" -m venv "$VENV_DIR" || fail "could not create the venv"
    fi
    # Siblings install from the working tree, not from a tag: this script runs
    # from a checkout, and installing the released tag here would silently
    # test something other than what is on disk.
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip || fail "pip self-upgrade"
    "$VENV_DIR/bin/pip" install --quiet "$UTILS_DIR/crdt-sync" \
        || fail "the crdt-sync sibling package"
    "$VENV_DIR/bin/pip" install --quiet --no-deps -e "$REPO_DIR" \
        || fail "freedays itself"
}

link_cli() {
    log "putting the freedays command on PATH at $BIN_DIR/freedays"
    mkdir -p "$BIN_DIR"
    ln -sf "$VENV_DIR/bin/freedays" "$BIN_DIR/freedays"
}

install_timer() {
    log "installing the sync timer"
    mkdir -p "$UNIT_DIR"
    install -m 644 "$REPO_DIR/systemd/freedays-sync.service" "$UNIT_DIR/"
    install -m 644 "$REPO_DIR/systemd/freedays-sync.timer" "$UNIT_DIR/"
    systemctl --user daemon-reload || fail "systemctl daemon-reload"
    systemctl --user enable --now freedays-sync.timer || fail "enabling the timer"
}

verify() {
    # The check that matters: the command resolves, and the gate apps'
    # interpreter can import the library. Those are two different
    # environments and either can be broken on its own.
    log "verifying"
    "$BIN_DIR/freedays" status >/dev/null || fail "the freedays CLI does not run"
    "$SYSTEM_PYTHON" -c "import freedays" 2>/dev/null || {
        log "NOTE: the system python cannot import freedays yet."
        log "      The gate apps need it there; their own install.sh does that."
    }
    if [[ "$INSTALL_TIMER" -eq 1 ]]; then
        systemctl --user is-enabled freedays-sync.timer >/dev/null \
            || fail "the sync timer is not enabled"
    fi
}

main() {
    build_venv
    link_cli
    if [[ "$INSTALL_TIMER" -eq 1 ]]; then
        install_timer
    fi
    verify

    echo "============================================================"
    "$BIN_DIR/freedays" status
    echo "============================================================"
    log "done. 'freedays mark today' takes the day off, everywhere."
    if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
        log "NOTE: $BIN_DIR is not on your PATH; add it to use 'freedays' bare."
    fi
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-timer)
            INSTALL_TIMER=0
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

main "$@"
