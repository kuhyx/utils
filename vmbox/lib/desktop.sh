#!/bin/bash
# ============================================================================
# vmbox: make a sandbox look like the host where the base image cannot.
#
#   vm lightdm <name>              lightdm autologin -> i3, tty1 a plain getty
#   vm shim <name> <tool> [mode]   fake a hardware tool (openrgb, nvidia-smi)
#
# Both mutate a live overlay and are undone by `vm reset`. Neither touches the
# golden image: rebuilding it would silently corrupt every existing sandbox.
# ============================================================================

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/ssh.sh"
source "$(dirname "${BASH_SOURCE[0]}")/launch.sh"

readonly DESKTOP_REBOOT_SSH_TIMEOUT="${VMBOX_DESKTOP_REBOOT_SSH_TIMEOUT:-150}"

_desktop_ensure_running() {
    local name="$1"
    if ! vm_is_running "$name"; then
        launch_vm "$name" >/dev/null
        vm_wait_ssh "$name" 150 || die "sandbox '$name' did not become reachable"
    fi
}

# Copy a guest/ script (plus any siblings it needs) in and run it as root.
_desktop_run_guest_script() {
    local name="$1" script="$2"; shift 2
    local f
    for f in "$script" "$@"; do
        vm_scp_to "$name" "$VMBOX_GUEST_DIR/$f" "/tmp/$f" ||
            die "could not copy $f into '$name'"
    done
    vm_ssh_exec "$name" "chmod +x /tmp/$script && sudo /tmp/$script $VMBOX_GUEST_USER"
}

# vm lightdm <name>
cmd_lightdm() {
    local name
    name="$(validate_vm_name "${1:-}")"
    require_vm "$name"
    _desktop_ensure_running "$name"

    log "Switching '$name' to lightdm autologin -> i3 (host topology)"
    _desktop_run_guest_script "$name" desktop-lightdm.sh vmbox-x11.sh ||
        die "lightdm switch failed in '$name'"

    # The switch only takes effect on a fresh boot: lightdm must own the seat
    # from the start, and the startx session on tty1 must never have run.
    # -no-reboot makes a guest reboot exit qemu, so relaunch it ourselves.
    log "Rebooting '$name' to bring lightdm up"
    vm_ssh_exec "$name" "sudo systemctl reboot" >/dev/null 2>&1 || true
    local waited=0
    while vm_is_running "$name" && (( waited < 60 )); do
        sleep 1; waited=$(( waited + 1 ))
    done
    vm_is_running "$name" && die "'$name' did not go down for the reboot"
    launch_vm "$name" >/dev/null
    vm_wait_ssh "$name" "$DESKTOP_REBOOT_SSH_TIMEOUT" ||
        die "'$name' did not come back after the reboot"

    # Prove the topology from the guest, not from the exit code: the unit is
    # active AND an Xorg it owns is up -- that is what a lockdown script sees.
    local state
    state="$(vm_ssh_exec "$name" "export VMBOX_X_WAIT=45; . /etc/profile.d/vmbox-x11.sh; \
        printf '%s %s %s' \"\$(systemctl is-active lightdm.service)\" \
        \"\$(systemctl is-enabled getty@tty1.service 2>/dev/null || echo -)\" \"\${DISPLAY:-none}\"" 2>/dev/null)"
    [[ "$state" == "active "*" :0" ]] ||
        die "lightdm did not come up cleanly in '$name' (lightdm/getty@tty1/DISPLAY: $state)"
    ok "'$name': lightdm.service active, autologin i3 session on ${state##* }"
}

# vm shim <name> <tool> [exit[:N]|hang|sleep:S]
cmd_shim() {
    local name tool mode
    name="$(validate_vm_name "${1:-}")"
    tool="${2:-}"; mode="${3:-exit}"
    [[ -n "$tool" ]] || die "usage: vm shim <name> <tool> [exit[:N]|hang|sleep:S]"
    require_vm "$name"
    _desktop_ensure_running "$name"

    vm_scp_to "$name" "$VMBOX_GUEST_DIR/shim.sh" "/tmp/shim.sh" ||
        die "could not copy shim.sh into '$name'"
    vm_ssh_exec "$name" "chmod +x /tmp/shim.sh && sudo /tmp/shim.sh '$tool' '$mode'" ||
        die "shim install failed in '$name'"
    ok "'$name': $tool is now a shim ($mode); calls logged to /var/log/vmbox-shim/$tool.log"
}
