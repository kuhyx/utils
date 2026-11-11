#!/bin/bash

# ============================================================================
# Install feedback-inbox for the current user: its own venv, the CLI on PATH,
# a todo-server token, and the systemd user units that watch every game's
# ~/data/<game>_binaries/feedback/ folder. Idempotent; rerun after any change.
#
# Enabling the units runs the inbox once (the sweep timer fires at once), so
# every bundle already on disk becomes a task: that is the backfill.
# Run the test suite first (scripts/run_subproject_tests.sh feedback_inbox).
# ============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR
readonly STATE_DIR="${HOME}/.local/share/feedback-inbox"
readonly VENV_DIR="${STATE_DIR}/venv"
readonly BIN_DIR="${HOME}/.local/bin"
readonly UNIT_DIR="${HOME}/.config/systemd/user"
readonly CONFIG_DIR="${HOME}/.config/feedback-inbox"
readonly TOKEN_FILE="${CONFIG_DIR}/token"
readonly MINT="${HOME}/src/todo/mcp/mint_token.sh"
readonly SYSTEM_PYTHON="/usr/bin/python3"
readonly UNITS=(
    feedback-inbox.service feedback-inbox.path
    feedback-inbox-sync.service feedback-inbox-sync.path feedback-inbox-sync.timer
)

log() { printf 'install: %s\n' "$1" >&2; }
fail() { printf 'install: FAILED -- %s\n' "$1" >&2; exit 1; }

build_venv() {
    log "building the venv at $VENV_DIR"
    mkdir -p "$STATE_DIR"
    [[ -x "$VENV_DIR/bin/python" ]] || "$SYSTEM_PYTHON" -m venv "$VENV_DIR" \
        || fail "could not create the venv"
    "$VENV_DIR/bin/pip" install --quiet --no-deps -e "$REPO_DIR" \
        || fail "feedback-inbox itself (stdlib only, no other packages)"
    mkdir -p "$BIN_DIR"
    ln -sf "$VENV_DIR/bin/feedback-inbox" "$BIN_DIR/feedback-inbox"
}

ensure_token() {
    # The service has no shell, so TODO_MCP_TOKEN from ~/.zshenv is invisible
    # to it. It gets its own revocable token (delete its line in
    # ~/.config/todo-mcp/tokens); the value goes straight to a 0600 file.
    [[ -s "$TOKEN_FILE" ]] && return 0
    [[ -x "$MINT" ]] || fail "$MINT is missing (the todo repo)"
    log "minting a todo-server token for feedback-inbox"
    mkdir -p "$CONFIG_DIR"
    (umask 077 && "$MINT" feedback-inbox >"$TOKEN_FILE") || fail "token mint"
    [[ -s "$TOKEN_FILE" ]] || fail "token file is empty"
}

install_units() {
    log "installing and enabling the units"
    mkdir -p "$UNIT_DIR"
    local unit
    for unit in "${UNITS[@]}"; do
        install -m 644 "$REPO_DIR/systemd/$unit" "$UNIT_DIR/"
    done
    systemctl --user daemon-reload || fail "daemon-reload"
    # Drop-ins first, so the paths are armed with every current game folder.
    "$VENV_DIR/bin/feedback-inbox" sync || fail "writing the watch lists"
    systemctl --user enable --now feedback-inbox.path feedback-inbox-sync.path \
        feedback-inbox-sync.timer || fail "enabling the units"
}

verify() {
    local unit
    for unit in feedback-inbox.path feedback-inbox-sync.path feedback-inbox-sync.timer; do
        systemctl --user is-active --quiet "$unit" || fail "$unit is not active"
    done
    log "ok: watching $(systemctl --user show feedback-inbox.path -p PathChanged \
        | tr ';' '\n' | grep -c feedback) feedback folder(s)"
}

main() {
    build_venv
    ensure_token
    install_units
    verify
}

main "$@"
