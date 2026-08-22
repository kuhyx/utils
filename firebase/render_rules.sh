#!/bin/bash

# ============================================================================
# Render deployable Realtime Database rules from the public template.
#
# The template in this repo carries a placeholder on purpose: the repository
# is public and the uid is the one value that must not appear in it. That
# leaves a trap -- publishing the template verbatim yields rules that match
# no account, which locks every app out of the shared project until someone
# notices. This script closes it: it substitutes the real uid from the local
# config and refuses to emit anything still containing a placeholder.
# ============================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_NAME
readonly SCRIPT_DIR
readonly TEMPLATE="$SCRIPT_DIR/database.rules.json"
readonly CONFIG_DIR="${CRDT_SYNC_CONFIG_DIR:-$HOME/.config/crdt-sync}"
readonly PLACEHOLDER="YOUR_FIREBASE_UID"

usage() {
    echo "Usage: $SCRIPT_NAME [--check]"
    echo "  (no args)  print deployable rules with the real uid substituted"
    echo "  --check    verify the rendered rules are sane; print nothing"
    exit 0
}

# The uid lives in firebase.json, the single source of truth for this machine.
read_uid() {
    local config="$CONFIG_DIR/firebase.json"
    if [[ ! -r "$config" ]]; then
        echo "Error: $config is missing or unreadable." >&2
        echo "It holds the uid these rules pin; see README.md." >&2
        exit 1
    fi
    python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['uid'])" \
        "$config"
}

render() {
    local uid="$1"
    sed "s/$PLACEHOLDER/$uid/g" "$TEMPLATE"
}

# Fail closed: a rules file that still names the placeholder, or that any
# unauthenticated request would satisfy, must never reach the console.
validate() {
    local rendered="$1"
    if [[ "$rendered" == *"$PLACEHOLDER"* ]]; then
        echo "Error: rendered rules still contain $PLACEHOLDER." >&2
        exit 1
    fi
    if ! grep -q 'auth != null' <<< "$rendered"; then
        echo "Error: rendered rules do not require authentication." >&2
        exit 1
    fi
    if ! grep -q "auth.uid ===" <<< "$rendered"; then
        echo "Error: rendered rules do not pin a uid; 'auth != null' alone" >&2
        echo "lets any stranger who self-registers read and write." >&2
        exit 1
    fi
    python3 -c "import json,sys; json.loads(sys.stdin.read())" <<< "$rendered"
}

main() {
    local check_only=false
    [[ "${1:-}" == "--check" ]] && check_only=true
    [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage

    local uid rendered
    uid="$(read_uid)"
    rendered="$(render "$uid")"
    validate "$rendered"

    if [[ "$check_only" == true ]]; then
        echo "Rules render cleanly and pin a uid." >&2
    else
        printf '%s\n' "$rendered"
    fi
}

main "$@"
