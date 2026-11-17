#!/bin/bash

# ============================================================================
# Install the app-errors CLI and its ingest timer for the current user.
#
# Own venv at ~/.local/share/app-errors/venv, the package installed editable
# from this checkout (run it from the live ~/src/utils, never a worktree).
# crdt-sync comes from the sibling directory, so the venv runs what is on disk.
# Idempotent: rerun it after any change. Exits non-zero unless the timer is
# active and one ingest pass over the local spool succeeds.
# ============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UTILS_DIR="$(dirname "$REPO_DIR")"
readonly REPO_DIR UTILS_DIR
readonly VENV_DIR="${HOME}/.local/share/app-errors/venv"
readonly BIN_DIR="${HOME}/.local/bin"
readonly UNIT_DIR="${HOME}/.config/systemd/user"
readonly TIMER="app-errors-ingest.timer"

log() { printf 'install: %s\n' "$1" >&2; }
fail() { printf 'install: FAILED -- %s\n' "$1" >&2; exit 1; }

build_venv() {
    [[ -x "$VENV_DIR/bin/python" ]] || /usr/bin/python3 -m venv "$VENV_DIR" || fail "venv"
    "$VENV_DIR/bin/pip" install --quiet "$UTILS_DIR/crdt-sync" || fail "crdt-sync"
    "$VENV_DIR/bin/pip" install --quiet --no-deps -e "$REPO_DIR" || fail "app-errors"
    mkdir -p "$BIN_DIR"
    ln -sf "$VENV_DIR/bin/app-errors" "$BIN_DIR/app-errors"
}

install_timer() {
    mkdir -p "$UNIT_DIR"
    install -m 0644 "$REPO_DIR/systemd/app-errors-ingest.service" "$REPO_DIR/systemd/$TIMER" "$UNIT_DIR/"
    systemctl --user daemon-reload
    systemctl --user enable --now "$TIMER"
}

verify() {
    systemctl --user is-active --quiet "$TIMER" || fail "$TIMER is not active"
    "$VENV_DIR/bin/app-errors" ingest --no-rtdb >/dev/null || fail "a spool-only ingest pass failed"
    log "ok: $TIMER active, ingest runs"
}

main() {
    log "installing app-errors from $REPO_DIR"
    build_venv
    install_timer
    verify
}

main "$@"
