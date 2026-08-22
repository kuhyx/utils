#!/bin/bash
# ============================================================================
# vmbox: capture the guest screen.
#
# Screenshots come from qemu's own framebuffer via QMP screendump, so no VNC
# or SPICE viewer is needed. This is how locker/i3 tests are verified -- and
# it is safer than testing on the host, where a fullscreen locker can hijack
# input and steal focus from whatever the user is doing.
# ============================================================================

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

vm_screenshot() {
    local name out
    name="$(validate_vm_name "${1:-}")"
    out="${2:-$PWD/${name}.png}"
    require_vm "$name"

    vm_is_running "$name" ||
        die "sandbox '$name' is not running (start it with: vm ssh $name)"

    python3 "$VMBOX_LIB_DIR/qmp.py" "$(vm_qmp_ctl "$name")" screendump "$out" >/dev/null ||
        die "screendump failed"

    [[ -s "$out" ]] || die "screendump produced an empty file"
    ok "screenshot: $out ($(du -h "$out" | cut -f1))"
    printf '%s' "$out"
}
