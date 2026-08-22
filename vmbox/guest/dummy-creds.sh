#!/bin/bash
# ============================================================================
# Provision SENTINEL credentials inside a sandbox.
#
# The guest must never hold real secrets: these repos reach live GitHub and
# Firebase, and a "test" run of an installer that syncs or pushes would hit
# production. Values are deliberately greppable, so if one ever shows up in a
# log or a request it is obvious where it came from.
# ============================================================================

set -euo pipefail

readonly SENTINEL="DUMMY-NOT-A-REAL-TOKEN-vmbox"

install -d -m 700 "$HOME/.config/crdt-sync"
cat > "$HOME/.config/crdt-sync/config.json" <<JSON
{
  "_comment": "vmbox sandbox credentials. Not real. Never sync with these.",
  "github_token": "$SENTINEL",
  "firebase_api_key": "$SENTINEL",
  "firebase_db_url": "https://vmbox-sandbox.invalid/"
}
JSON
chmod 600 "$HOME/.config/crdt-sync/config.json"

# A throwaway ssh key so anything expecting one finds it, without ever
# granting access to a real host.
if [[ ! -f "$HOME/.ssh/id_ed25519" ]]; then
    install -d -m 700 "$HOME/.ssh"
    ssh-keygen -t ed25519 -N '' -q -C 'vmbox-sandbox-throwaway' \
        -f "$HOME/.ssh/id_ed25519"
fi

git config --global user.name  "vmbox sandbox"
git config --global user.email "sandbox@vmbox.invalid"
# Any push attempt should fail loudly rather than reach a real remote.
git config --global url."https://vmbox-blocked.invalid/".insteadOf "https://github.com/"

echo "sandbox credentials provisioned (all sentinel values)"
