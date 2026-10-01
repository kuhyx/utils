#!/bin/bash
# ============================================================================
# vmbox: `vm hibernate-setup <name>` -- make a sandbox able to hibernate and
# resume. Overlay only: the sealed base is never rebuilt for this, because
# `vm build --force` re-seals a new checksum under every existing sandbox.
# ============================================================================

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
# shellcheck source=launch.sh
source "$(dirname "${BASH_SOURCE[0]}")/launch.sh"
# shellcheck source=ssh.sh
source "$(dirname "${BASH_SOURCE[0]}")/ssh.sh"

readonly HIBERNATE_GUEST_SCRIPT="/var/tmp/vmbox-hibernate-setup.sh"
readonly HIBERNATE_X11_PROFILE="/var/tmp/vmbox-x11.sh"

_hibernate_boot() {
    local name="$1"
    launch_vm "$name" >/dev/null
    vm_wait_ssh "$name" 150 || die "sandbox '$name' did not become reachable"
}

# Clean poweroff, then wait for qemu to go. Not `vm run`: its exit-code
# recovery would boot the guest again behind our back.
_hibernate_poweroff() {
    local name="$1" waited=0
    vm_ssh_exec "$name" 'sudo systemctl poweroff' </dev/null >/dev/null 2>&1 || true
    while vm_is_running "$name" && (( waited < 90 )); do
        sleep 1; waited=$(( waited + 1 ))
    done
    vm_is_running "$name" && die "sandbox '$name' did not power off within 90s"
    return 0
}

cmd_hibernate_setup() {
    local name swap_mb=0
    name="$(validate_vm_name "${1:-}")"; shift || true
    require_vm "$name"
    if [[ "${1:-}" == --swap-mb ]]; then
        swap_mb="${2:-}"; [[ "$swap_mb" =~ ^[0-9]+$ ]] || die "--swap-mb needs MiB"
    fi

    vm_is_running "$name" || _hibernate_boot "$name"
    vm_scp_to "$name" "$VMBOX_GUEST_DIR/hibernate-setup.sh" "$HIBERNATE_GUEST_SCRIPT" ||
        die "could not copy the setup script in"
    vm_scp_to "$name" "$VMBOX_GUEST_DIR/vmbox-x11.sh" "$HIBERNATE_X11_PROFILE" ||
        die "could not copy vmbox-x11.sh in"
    vm_ssh_exec "$name" "sudo bash $HIBERNATE_GUEST_SCRIPT $swap_mb $HIBERNATE_X11_PROFILE" </dev/null ||
        die "hibernate setup failed in the guest"

    # The cmdline only takes effect on the next boot.
    log "Rebooting '$name' so the new kernel cmdline applies"
    _hibernate_poweroff "$name"
    _hibernate_boot "$name"

    # Prove it rather than assume it: the running kernel carries the resume
    # args (and no-kvmclock, so a resume reads the RTC), and logind (what
    # `systemctl hibernate` asks) says yes.
    vm_ssh_exec "$name" 'grep -q "resume_offset=.*no-kvmclock" /proc/cmdline' </dev/null ||
        die "the guest booted without resume_offset=/no-kvmclock on its cmdline"
    local can
    # sudo: polkit denies CanHibernate to a non-seat ssh session.
    can="$(vm_ssh_exec "$name" 'sudo busctl call org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager CanHibernate' </dev/null)"
    [[ "$can" == 's "yes"' ]] || die "logind CanHibernate says: ${can:-nothing}"
    ok "'$name' can hibernate and resume (logind CanHibernate=yes)"
}
