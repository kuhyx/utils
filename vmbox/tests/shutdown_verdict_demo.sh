#!/bin/bash

# ============================================================================
# vmbox: the headline test -- "does shutdown.sh really shut the machine down?"
#
# Exercises every branch of the verdict table against a REAL guest, including
# the failure modes. A verifier that has only ever returned "pass" is untested,
# so the reboot / panic cases matter as much as the clean one.
# ============================================================================

set -uo pipefail

VMBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly VMBOX_ROOT
readonly VM="${VM:-verdict}"
readonly VM_CLI="$VMBOX_ROOT/bin/vm"

pass=0
fail=0

step()  { printf '\n\033[0;34m=== %s\033[0m\n' "$*"; }
expect() {
    local label="$1" want="$2" got="$3"
    if [[ "$got" == *"$want"* ]]; then
        printf '\033[0;32m  PASS\033[0m %s\n' "$label"
        pass=$(( pass + 1 ))
    else
        printf '\033[0;31m  FAIL\033[0m %s\n    wanted verdict: %s\n    got: %s\n' \
            "$label" "$want" "$got"
        fail=$(( fail + 1 ))
    fi
}

reset_vm() { "$VM_CLI" reset "$VM" >/dev/null 2>&1 || "$VM_CLI" new "$VM" >/dev/null 2>&1; }

"$VM_CLI" rm "$VM" >/dev/null 2>&1
"$VM_CLI" new "$VM" --rtc 2026-08-22T20:55:00

step "1. A genuine, clean poweroff"
out="$("$VM_CLI" run "$VM" 'sudo systemctl poweroff' 2>&1)"
printf '%s\n' "$out" | tail -4
expect "clean poweroff is recognised" "clean poweroff" "$out"

step "2. A script that REBOOTS instead of powering off"
reset_vm
out="$("$VM_CLI" run "$VM" 'sudo systemctl reboot' 2>&1)"
printf '%s\n' "$out" | tail -4
expect "reboot is not mistaken for a shutdown" "REBOOTED" "$out"

step "3. A hard kernel panic"
reset_vm
out="$("$VM_CLI" run "$VM" 'echo c | sudo tee /proc/sysrq-trigger' 2>&1)"
printf '%s\n' "$out" | tail -4
expect "panic is distinguished from a clean stop" "PANIC" "$out"

step "4. A command that does NOT stop the machine"
reset_vm
out="$("$VM_CLI" run "$VM" 'echo still-here' 2>&1)"
printf '%s\n' "$out" | tail -4
expect "a live guest is reported as still running" "still running" "$out"

printf '\n\033[0;34m=== RESULT: %d passed, %d failed\033[0m\n' "$pass" "$fail"
exit $(( fail > 0 ? 1 : 0 ))
