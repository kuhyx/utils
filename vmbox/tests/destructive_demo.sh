#!/bin/bash

# ============================================================================
# vmbox end-to-end demo: break a sandbox as thoroughly as possible, verify the
# breakage, reset it, and prove the host was never touched.
#
# This is the acceptance test for the whole tool. It is deliberately
# destructive INSIDE the guest -- that is the point -- and it asserts after
# each step rather than just printing output.
# ============================================================================

set -uo pipefail

VMBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly VMBOX_ROOT
readonly VM="${VM:-destruct}"
readonly VM_CLI="$VMBOX_ROOT/bin/vm"

# Host-side facts captured up front, re-checked at the end.
HOST_HOSTS_ATTRS="$(lsattr /etc/hosts 2>/dev/null | awk '{print $1}')"
readonly HOST_HOSTS_ATTRS
BASE_SHA_BEFORE="$(sha256sum "$HOME/.local/share/vmbox/base/base.qcow2" 2>/dev/null | awk '{print $1}')"
readonly BASE_SHA_BEFORE

pass=0
fail=0

step() { printf '\n\033[0;34m=== %s\033[0m\n' "$*"; }
check() {
    local label="$1" expected="$2" actual="$3"
    if [[ "$actual" == *"$expected"* ]]; then
        printf '\033[0;32m  PASS\033[0m %s\n' "$label"
        pass=$(( pass + 1 ))
    else
        printf '\033[0;31m  FAIL\033[0m %s\n    wanted: %s\n    got:    %s\n' \
            "$label" "$expected" "$actual"
        fail=$(( fail + 1 ))
    fi
}

step "0. Fresh sandbox, clock pinned into the shutdown window"
"$VM_CLI" rm "$VM" >/dev/null 2>&1
"$VM_CLI" new "$VM" --rtc 2026-08-22T20:55:00

step "1. Baseline: the guest is a healthy Arch system"
out="$("$VM_CLI" run "$VM" 'cat /etc/os-release | head -1' 2>&1)"
check "guest is Arch Linux" "Arch Linux" "$out"

step "2. DESTROY: wipe /etc and /usr"
"$VM_CLI" run "$VM" 'sudo rm -rf --no-preserve-root /etc /usr 2>/dev/null; true' 2>&1 | tail -3

step "3. Confirm the guest really is broken"
out="$("$VM_CLI" run "$VM" 'cat /etc/os-release 2>&1 || echo GUEST_IS_BROKEN' 2>&1)"
check "guest is destroyed" "GUEST_IS_BROKEN" "$out"

step "4. RESET -- one command"
time_start=$SECONDS
"$VM_CLI" reset "$VM"
printf '  reset took %ds\n' "$(( SECONDS - time_start ))"

step "5. Confirm the sandbox is pristine again"
out="$("$VM_CLI" run "$VM" 'cat /etc/os-release | head -1' 2>&1)"
check "guest restored to Arch Linux" "Arch Linux" "$out"

step "6. THE HOST MUST BE UNTOUCHED"
now_attrs="$(lsattr /etc/hosts 2>/dev/null | awk '{print $1}')"
check "host /etc/hosts attributes unchanged" "$HOST_HOSTS_ATTRS" "$now_attrs"
now_sha="$(sha256sum "$HOME/.local/share/vmbox/base/base.qcow2" 2>/dev/null | awk '{print $1}')"
check "base image unmodified" "$BASE_SHA_BEFORE" "$now_sha"
check "host /etc still exists" "PRESENT" "$([[ -d /etc && -d /usr ]] && echo PRESENT)"

printf '\n\033[0;34m=== RESULT: %d passed, %d failed\033[0m\n' "$pass" "$fail"
exit $(( fail > 0 ? 1 : 0 ))
