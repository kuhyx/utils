#!/bin/bash
# ============================================================================
# vmbox: cloud-init NoCloud seed ISO generation.
#
# The seed ISO is how the golden image gets its user, SSH key and provisioning
# script. It is used ONLY during `vm build`; the sealed base disables
# cloud-init, so per-VM boots never touch it.
# ============================================================================

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# Generate the throwaway keypair the host uses to reach guests. This key is
# sandbox-only and is never the user's real ~/.ssh key.
seed_ensure_key() {
    [[ -f "$VMBOX_SSH_KEY" ]] && return 0
    log "Generating sandbox SSH key (throwaway, sandbox-only)"
    install -d -m 700 "$VMBOX_BASE_DIR"
    ssh-keygen -t ed25519 -N '' -q -C 'vmbox-sandbox-key' -f "$VMBOX_SSH_KEY"
    ok "key: $VMBOX_SSH_KEY"
}

# Write user-data + meta-data and pack them into a CIDATA volume.
# $1 = output ISO path, $2 = directory to build in.
seed_build_iso() {
    local iso="$1" workdir="$2" pubkey
    pubkey="$(cat "${VMBOX_SSH_KEY}.pub")"

    # NOPASSWD sudo is load-bearing, not a convenience: without it every
    # `vm run` that uses sudo blocks forever on an invisible password prompt.
    cat > "$workdir/user-data" <<UD
#cloud-config
users:
  - name: ${VMBOX_GUEST_USER}
    groups: [wheel]
    shell: /bin/bash
    sudo: ["ALL=(ALL) NOPASSWD:ALL"]
    lock_passwd: false
    ssh_authorized_keys:
      - ${pubkey}

# Password login on the serial console, for debugging a guest whose sshd is
# broken. Harmless: the VM is unreachable from outside the host.
chpasswd:
  expire: false
  list: |
    ${VMBOX_GUEST_USER}:vmbox
    root:vmbox

ssh_pwauth: true
preserve_hostname: false

UD

    cat > "$workdir/meta-data" <<MD
instance-id: vmbox-golden
local-hostname: vmbox
MD

    xorrisofs -output "$iso" -volid CIDATA -joliet -rational-rock \
        -quiet "$workdir/user-data" "$workdir/meta-data"
    [[ -s "$iso" ]] || die "seed ISO generation produced an empty file"
}
