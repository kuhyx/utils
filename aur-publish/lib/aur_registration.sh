#!/bin/bash

# ============================================================================
# Waiting for AUR registration and SSH access to come up.
#
# Sourced by publish.sh, never executed: these functions read the readonly
# config (AUR_HOST, SSH_KEY, GATE, POLL_SECONDS) that the entry script declares, and
# a `readonly` re-run inside a twice-sourced lib would abort under `set -e`.
# ============================================================================

set -euo pipefail

register_status() {
    python3 "$GATE" /register 2>/dev/null | head -1
}

open_browser() {
    local url="$1"
    local browser
    for browser in xdg-open thorium-browser chromium google-chrome-stable firefox librewolf; do
        if command -v "$browser" >/dev/null 2>&1; then
            "$browser" "$url" >/dev/null 2>&1 &
            info "Opened $url in $browser"
            return 0
        fi
    done
    warn "No browser found; open this yourself: $url"
}

ensure_key() {
    if [[ ! -f "$SSH_KEY" ]]; then
        log "Generating an AUR SSH key (none at $SSH_KEY)"
        ssh-keygen -t ed25519 -f "$SSH_KEY" -N '' -C 'kuhy@aur'
    fi
    if ! grep -q "Host $AUR_HOST" "$HOME/.ssh/config" 2>/dev/null; then
        log "Adding $AUR_HOST to ~/.ssh/config"
        mkdir -p "$HOME/.ssh"
        cat >> "$HOME/.ssh/config" <<EOF

# AUR uses a dedicated key so it stays separate from the GitHub identity.
Host $AUR_HOST
    User aur
    IdentityFile $SSH_KEY
    IdentitiesOnly yes
EOF
        chmod 600 "$HOME/.ssh/config"
    fi
}

ssh_works() {
    # The AUR refuses interactive shells; "Interactive shell is disabled" on a
    # successful key auth is the success signal, not an error.
    ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
        -o ConnectTimeout=15 "aur@$AUR_HOST" help 2>&1 |
        grep -qiE 'interactive shell is disabled|Welcome to AUR'
}

wait_for_registration() {
    local status
    status="$(register_status)"
    if [[ "$status" == "200" ]]; then
        log "AUR registration is OPEN"
    else
        log "AUR registration is closed (HTTP $status). Polling every ${POLL_SECONDS}s."
        info "Ctrl-C to stop; re-run any time, nothing is lost."
        while :; do
            sleep "$POLL_SECONDS"
            status="$(register_status)"
            if [[ "$status" == "200" ]]; then
                log "Registration is BACK (HTTP 200)"
                break
            fi
            printf '    %s still HTTP %s\n' "$(date +%H:%M)" "$status"
        done
    fi

    open_browser "https://$AUR_HOST/register"
    cat <<EOF

    ------------------------------------------------------------------
    Sign up, and paste this into the "SSH Public Key" field:

$(sed 's/^/      /' "$SSH_KEY.pub")

    You will need to confirm the address from your email before the
    account works. This script waits for that automatically.
    ------------------------------------------------------------------
EOF
}

wait_for_ssh() {
    log "Waiting for the SSH key to authenticate against the AUR"
    local waited=0
    until ssh_works; do
        sleep 30
        waited=$((waited + 30))
        if ((waited % 300 == 0)); then
            info "still waiting ($((waited / 60)) min) — key not accepted yet"
        fi
    done
    log "SSH authentication OK"
}

# ---------------------------------------------------------------------------
# Phase 2: build, verify and publish one package
# ---------------------------------------------------------------------------

