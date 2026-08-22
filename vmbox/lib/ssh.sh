#!/bin/bash
# ============================================================================
# vmbox: ssh access to a sandbox.
#
# Guest host keys are deliberately NOT verified and NOT recorded: a sandbox is
# reset constantly, so a real known_hosts entry would collide on every reset.
# Isolation comes from the VM boundary, not from ssh key continuity.
# ============================================================================

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

vm_ssh_port() {
    local port
    port="$(meta_get "$1" ssh_port)" || die "sandbox '$1' has no ssh port in meta"
    printf '%s' "$port"
}

_ssh_base_args() {
    local port="$1"
    printf '%s\0' \
        -i "$VMBOX_SSH_KEY" \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o GlobalKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -o ConnectTimeout="${VMBOX_SSH_CONNECT_TIMEOUT:-5}" \
        -o ServerAliveInterval=5 \
        -p "$port"
}

# Run a command in the guest. Returns the guest's exit code, EXCEPT when the
# connection dies -- ssh reports 255 for a dropped link, a killed sshd and a
# successful poweroff alike, which is exactly why the verdict logic never
# trusts this return value on its own.
vm_ssh_exec() {
    local name="$1"; shift
    local port; port="$(vm_ssh_port "$name")"
    local -a args=()
    mapfile -d '' -t args < <(_ssh_base_args "$port")
    ssh "${args[@]}" "${VMBOX_GUEST_USER}@127.0.0.1" "$@"
}

vm_ssh_interactive() {
    local name
    name="$(validate_vm_name "${1:-}")"; shift || true
    require_vm "$name"

    if ! vm_is_running "$name"; then
        log "Sandbox '$name' is not running; starting it"
        source "$VMBOX_LIB_DIR/launch.sh"
        launch_vm "$name"
        vm_wait_ssh "$name" 120 || die "sandbox '$name' did not become reachable"
    fi

    local port; port="$(vm_ssh_port "$name")"
    local -a args=()
    mapfile -d '' -t args < <(_ssh_base_args "$port")
    # -t forces a pty so interactive tools (and sudo prompts) behave.
    ssh -t "${args[@]}" "${VMBOX_GUEST_USER}@127.0.0.1" "$@"
}

vm_scp_to() {
    local name="$1" src="$2" dest="$3" port
    port="$(vm_ssh_port "$name")"
    scp -i "$VMBOX_SSH_KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR -P "$port" -r "$src" "${VMBOX_GUEST_USER}@127.0.0.1:$dest"
}

# Poll until the guest answers. ssh is its own port prober, so this needs no
# nc/socat (neither is installed on this host).
vm_wait_ssh() {
    local name="$1" timeout="${2:-120}" deadline start now
    # Deadline is WALL CLOCK, not a count of sleeps. Each failed probe also
    # burns up to ConnectTimeout seconds inside ssh itself, so counting only
    # the sleeps under-measures badly: a guest that never boots (no kernel,
    # stuck in GRUB) made a nominal 150s wait run for well over 10 minutes,
    # which reads as a hung tool rather than an unreachable sandbox.
    printf -v start '%(%s)T' -1
    deadline=$(( start + timeout ))
    while :; do
        printf -v now '%(%s)T' -1
        (( now < deadline )) || return 1
        # A 1s connect timeout (not the 5s default) is what makes this loop
        # track the guest instead of lagging ~35s behind it. QEMU's user-mode
        # networking ACCEPTS the forwarded TCP connection even while the guest
        # has nothing listening on :22, so a probe against a booting guest does
        # not fail fast -- it blocks for the whole ConnectTimeout. Measured:
        # sshd is reachable at ~10s, but a 5s-timeout poll reported the guest
        # up at ~45s, and that inflated figure was blamed on cloud-init.
        #
        # It goes through the env var because ssh honours the FIRST value given
        # for an option, so a second -o appended here would be ignored -- and
        # anything after the hostname is the remote command, not an option.
        if vm_is_running "$name" &&
           VMBOX_SSH_CONNECT_TIMEOUT=1 vm_ssh_exec "$name" -o BatchMode=yes true 2>/dev/null; then
            return 0
        fi
        # A qemu that has exited means the guest will never answer.
        if ! vm_is_running "$name"; then
            (( now - start > 3 )) && return 1
        fi
        sleep 1
    done
}
