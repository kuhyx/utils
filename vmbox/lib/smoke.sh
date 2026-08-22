#!/bin/bash
# ============================================================================
# vmbox: post-seal verification.
#
# Split out of base.sh to stay under the 250-line cap.
# ============================================================================

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# Boot a real overlay off the freshly sealed base and require that ssh answers.
#
# This is the gate that matters. Every check inside the build VM only proves
# state at seal time; the failures that actually shipped all lived in the gap
# between "correct in the build VM" and "works on a fresh overlay boot". This
# catches missing host keys, a no-op systemctl enable, a clobbered NIC and
# whatever the next cause turns out to be, WITHOUT needing to know which.
base_smoke_test() {
    log "Smoke-testing the sealed image (boots a throwaway sandbox)"
    source "$VMBOX_LIB_DIR/overlay.sh"
    source "$VMBOX_LIB_DIR/launch.sh"
    source "$VMBOX_LIB_DIR/ssh.sh"

    local smoke="__smoke"
    vm_exists "$smoke" && overlay_rm "$smoke" >/dev/null 2>&1
    overlay_new "$smoke" >/dev/null

    local failed=0
    launch_vm "$smoke" >/dev/null
    if vm_wait_ssh "$smoke" 180 && vm_ssh_exec "$smoke" true 2>/dev/null; then
        ok "smoke test passed: a fresh sandbox boots and accepts ssh"
    else
        failed=1
        warn "SMOKE TEST FAILED -- the sealed image boots but is unreachable."
        warn "Serial log: $(vm_serial "$smoke" 0)"
        warn "Debug it with the serial console (root autologin is enabled there)."
    fi

    # On failure KEEP the sandbox: deleting it would destroy the serial log
    # this very message points at, which is the only evidence available when
    # ssh is the thing that is broken.
    if (( failed == 0 )); then
        overlay_rm "$smoke" >/dev/null 2>&1 || true
    else
        warn "keeping sandbox '__smoke' so its logs survive; remove it with: vm rm __smoke"
        die "refusing to ship an unreachable base image"
    fi
}

