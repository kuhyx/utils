#!/bin/bash
# Registers the Desktop OAuth client (no API exists, so one console step stays
# manual), stores its JSON privately, then proves Firebase accepts its tokens.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly SCRIPT_DIR REPO_DIR
readonly PROJECT="kuhy-syncs"
readonly ACCOUNT="321krzychu@gmail.com"
readonly CONSOLE_URL="https://console.cloud.google.com/auth/clients?project=${PROJECT}&authuser=${ACCOUNT}"
readonly APP_TYPE="Desktop app"
readonly CLIENT_NAME="crdt-sync desktop/android PKCE"
readonly PAUSE_SECONDS="${PAUSE_SECONDS:-12}"
readonly WAIT_SECONDS="${WAIT_SECONDS:-900}"
readonly PROBE_TRIES="${PROBE_TRIES:-12}"
readonly PROBE_GAP_SECONDS="${PROBE_GAP_SECONDS:-30}"

log() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
step() { printf '   %s\n' "$1"; }

usage() {
    cat <<EOF
Usage: $(basename "$0") [--verify-only | --dry-run | --help]

  (no flag)      open the console, clipboard-feed the form, pick up the
                 downloaded JSON, store it, then verify
  --verify-only  skip registration; probe, consent flow, signInWithIdp
  --dry-run      print the plan; open, copy and write nothing

Your part: Application type = Desktop app, paste the name, CREATE, DOWNLOAD
JSON in the dialog; later tap Allow on the consent page.
Stored at ~/.config/crdt-sync/desktop_client.json (mode 600).
EOF
}

# Prints the value always, so this works over ssh with no X display too.
clip() {
    if command -v xclip >/dev/null 2>&1 && [[ -n "${DISPLAY:-}" ]]; then
        printf '%s' "$1" | xclip -selection clipboard 2>/dev/null || true
        printf '   \033[32m[copied]\033[0m %s\n' "$1"
    else
        printf '   %s\n' "$1"
    fi
}

# Without a terminal (e.g. run via `!`) read would hit EOF at once.
pause() {
    if [[ -t 0 ]]; then
        read -rp "   ...press Enter once pasted " _ || true
    else
        sleep "$PAUSE_SECONDS"
    fi
}

open_console() {
    if command -v xdg-open >/dev/null 2>&1; then
        setsid xdg-open "$CONSOLE_URL" >/dev/null 2>&1 &
    else
        step "open: $CONSOLE_URL"
    fi
}

run_tool() { (cd "$REPO_DIR" && python3 -m "tool.$1" "${@:2}"); }

wait_for_propagation() {
    local try
    for ((try = 1; try <= PROBE_TRIES; try++)); do
        if run_tool verify_desktop_client --probe-only; then
            return 0
        fi
        step "probe $try/$PROBE_TRIES failed; new clients need a few minutes"
        sleep "$PROBE_GAP_SECONDS"
    done
    echo "error: client still not accepted; rerun with --verify-only later" >&2
    return 1
}

verify() {
    log "Verifying: probe, consent flow, Firebase signInWithIdp"
    step "Tap Allow on the sync account's consent page when it opens."
    run_tool verify_desktop_client
}

register() {
    local started
    started="$(date +%s)"
    log "Create ONE Desktop OAuth client in project $PROJECT"
    open_console
    sleep 2
    step "Click '+ CREATE CLIENT'. Application type (paste or pick):"
    clip "$APP_TYPE"
    pause
    step "Field 'Name':"
    clip "$CLIENT_NAME"
    pause
    step "Click CREATE, then DOWNLOAD JSON in the dialog (the secret shows once)."
    step "Leave the existing Web and Android clients alone."
    log "Waiting up to ${WAIT_SECONDS}s for the downloaded client_secret_*.json"
    run_tool desktop_client pickup --since "$started" --timeout "$WAIT_SECONDS"
    wait_for_propagation
    verify
}

dry_run() {
    log "Dry run: nothing is opened, copied or written"
    step "page:      $CONSOLE_URL"
    step "type:      $APP_TYPE"
    step "name:      $CLIENT_NAME"
    step "stores at: ~/.config/crdt-sync/desktop_client.json (mode 600)"
    step "verify:    python3 -m tool.verify_desktop_client (in $REPO_DIR)"
}

main() {
    case "${1:-}" in
        --verify-only) verify ;;
        --dry-run) dry_run ;;
        -h | --help) usage ;;
        "") register ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
}

main "$@"
