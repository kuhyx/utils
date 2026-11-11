#!/bin/bash

# ============================================================================
# Deploy the parts of utils that run on this machine, then prove they are live.
#
# utils is mostly libraries that apps pin by git tag, so "deploy" means:
#   1. every released library's tag for its current version is on origin
#      (sickdays, sync_settings_ui: the apps' pins resolve to the code on main);
#   2. the sickdays CLI + launcher run the checkout's code, via
#      sickdays/install.sh (its venv installs sickdays editable from here).
#
# Run it from the live checkout (~/src/utils), never from a worktree: install.sh
# installs editable from its own directory, and a worktree path would point the
# live venv at a directory that gets deleted.
#
# Usage: scripts/deploy.sh [--verify-only]
# Exits non-zero unless every health check passes. Idempotent.
# ============================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
UTILS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SCRIPT_NAME UTILS_DIR
readonly VENV_DIR="${HOME}/.local/share/sickdays/venv"
readonly CLI_LINK="${HOME}/.local/bin/sickdays"

VERIFY_ONLY=0
FAILED=0

log() { printf 'deploy: %s\n' "$1" >&2; }
bad() { printf 'deploy: FAIL -- %s\n' "$1" >&2; FAILED=1; }

usage() {
    echo "Usage: $SCRIPT_NAME [--verify-only]"
    echo "  --verify-only  run the health checks without installing anything"
    exit 0
}

# Prints the version field of a pyproject.toml or pubspec.yaml.
manifest_version() {
    sed -nE 's/^version( =|:) *"?([^"]+)"?$/\2/p' "$1" | head -n 1
}

# The tag <prefix>-v<version> for the version on disk must be on origin and
# hold exactly this checkout's <dir>: code past its tag never reaches the apps
# that pin it.
check_tag() {
    local prefix="$1" dir="$2" manifest version tag
    manifest="$UTILS_DIR/$dir/pyproject.toml"
    [[ -f "$manifest" ]] || manifest="$UTILS_DIR/$dir/pubspec.yaml"
    version="$(manifest_version "$manifest")"
    tag="${prefix}-v${version}"
    if ! git -C "$UTILS_DIR" fetch -q origin "+refs/tags/${tag}:refs/tags/${tag}" 2>/dev/null; then
        bad "${tag} is not on origin: tag and push it so the app pins resolve"
    elif [[ "$(git -C "$UTILS_DIR" rev-parse "${tag}:${dir}")" \
        != "$(git -C "$UTILS_DIR" rev-parse "HEAD:${dir}")" ]]; then
        bad "${dir} changed after ${tag}: bump its version and release it"
    else
        log "ok: ${tag} is on origin and matches HEAD"
    fi
}

# The bare `sickdays` (what the launcher runs) must be the venv's CLI, and the
# venv must import the text-free sickdays from this checkout.
check_sickdays() {
    local target module
    target="$(readlink -f "$CLI_LINK" || true)"
    if [[ "$target" != "$(readlink -f "$VENV_DIR/bin/sickdays")" ]]; then
        bad "$CLI_LINK runs ${target:-nothing}, not the venv's sickdays"
    fi
    module="$("$VENV_DIR/bin/python" -I -c 'import sickdays; print(sickdays.__file__)' 2>/dev/null || true)"
    if [[ "$module" != "$UTILS_DIR/sickdays/"* ]]; then
        bad "the sickdays venv imports ${module:-nothing}, not $UTILS_DIR/sickdays"
    elif [[ -e "$(dirname "$module")/gui/_text.py" ]]; then
        bad "the live sickdays still has gui/_text.py (the pre-text-free GUI)"
    else
        log "ok: sickdays runs $module"
    fi
}

verify() {
    check_tag sickdays sickdays
    check_tag sync_settings_ui sync_settings_ui
    check_sickdays
    if [[ "$FAILED" -ne 0 ]]; then
        log "health check FAILED"
        exit 1
    fi
    log "healthy"
}

main() {
    if [[ "$VERIFY_ONLY" -eq 0 ]]; then
        log "installing sickdays from $UTILS_DIR/sickdays"
        "$UTILS_DIR/sickdays/install.sh"
    fi
    verify
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --verify-only) VERIFY_ONLY=1; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

main
