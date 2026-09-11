#!/bin/bash

# ============================================================================
# Replace the Web OAuth client secret and reseed one app's Firebase session.
#
# When seed_session fails with `invalid_client: The provided client secret is
# invalid`, the secret in ~/.config/crdt-sync/oauth_client_secret no longer
# matches the Web client in the Google Cloud console (it was rotated there).
# There is no API for that secret -- gcloud has no command and the Firebase
# CLI has none -- so the one human step is copying it from the console page.
# This opens that exact page, reads the pasted secret without echoing it,
# writes the file, and immediately runs the seed so a wrong paste fails here
# and not on the next systemd tick.
#
# Usage: tool/refresh_oauth_secret.sh --app <name> [--app <name> ...]
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly SCRIPT_DIR REPO_DIR
readonly CONFIG_DIR="$HOME/.config/crdt-sync"
readonly SECRET_FILE="$CONFIG_DIR/oauth_client_secret"
# The project's Web client, the same id every companion app ships as its
# google_sign_in serverClientId.
readonly CLIENT_ID="845446124781-prdoherj0v64vc6egvvcp3l0693khaur.apps.googleusercontent.com"
readonly CONSOLE_URL="https://console.cloud.google.com/apis/credentials?project=kuhy-syncs"

APPS=()

usage() {
    echo "Usage: $(basename "$0") --app <name> [--app <name> ...]"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --app) APPS+=("$2"); shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done
[[ ${#APPS[@]} -gt 0 ]] || { echo "Error: at least one --app is required" >&2; exit 1; }

main() {
    echo "1. Opening the credentials page. Under 'OAuth 2.0 Client IDs' open the"
    echo "   Web client (id starts with ${CLIENT_ID%%-*}-prdoh...) and copy its"
    echo "   Client secret. If it says the secret was rotated, copy the NEW one."
    xdg-open "$CONSOLE_URL" </dev/null >/dev/null 2>&1 || echo "   (open manually: $CONSOLE_URL)"

    echo "2. Paste it here and press Enter (not shown):"
    local secret
    # -s needs a terminal; piped input (tests) falls back to a plain read.
    if [[ -t 0 ]]; then read -rs secret; echo; else read -r secret; fi
    if [[ ! $secret =~ ^GOCSPX-[A-Za-z0-9_-]{28}$ ]]; then
        echo "Error: that does not look like a Web client secret (GOCSPX-…, 35 chars)" >&2
        exit 1
    fi

    mkdir -p "$CONFIG_DIR"
    (umask 077; printf '%s' "$secret" > "$SECRET_FILE")
    echo "3. Saved to $SECRET_FILE. Running the seed -- pick the sync account in the browser."

    local app_args=()
    for app in "${APPS[@]}"; do app_args+=(--app "$app"); done
    (
        cd "$REPO_DIR"
        python3 -m tool.seed_session \
            --client-id "$CLIENT_ID" \
            --client-secret "$secret" \
            "${app_args[@]}"
    )
}

main "$@"
