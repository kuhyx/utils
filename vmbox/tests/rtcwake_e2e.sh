#!/bin/bash
# ============================================================================
# vmbox: end-to-end proof of `vm wake` (RTC wake emulation), on a real guest.
#
#   A. poweroff:  arm `rtcwake -m no -s 120`, power off; the harness must find
#      the alarm in the stopped guest's CMOS, power it on at that instant,
#      and the guest's boot-time unit must run AFTER the armed instant.
#   B. hibernate: same, but `systemctl hibernate`; the guest must RESUME
#      (same boot_id, a pre-hibernate process still alive, the post-resume
#      hook ran after the armed instant) and survive a watchdog window.
#   C. negative control: arm, then `rtcwake -m disable`, power off; the
#      harness must refuse to power it on (exit 9). A harness that has only
#      ever woken a machine is untested.
#
# Usage: tests/rtcwake_e2e.sh [--uefi] [--keep]
# Env:   VM (sandbox, default rtcwake), ACCEL_POWEROFF (default 1: a real
#        two-minute wait), ACCEL_HIBERNATE (default 10), VMBOX_MEM (2048).
# Run it under ~/.claude/scripts/capped.sh (CAP_MEM=4G CAP_CPU_PCT=20).
# ============================================================================

set -euo pipefail

VMBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly VMBOX_ROOT
readonly VM_CLI="$VMBOX_ROOT/bin/vm"
readonly VM="${VM:-rtcwake}"
readonly ACCEL_POWEROFF="${ACCEL_POWEROFF:-1}"
readonly ACCEL_HIBERNATE="${ACCEL_HIBERNATE:-10}"
# Small enough for capped.sh's 4G ceiling, and swap is sized from it.
export VMBOX_MEM="${VMBOX_MEM:-2048}"
readonly PROBE=/var/tmp/rtcwake_guest_probe.sh
readonly ARM='sudo rtcwake -m no -s 120 >/dev/null && sudo cp /sys/class/rtc/rtc0/wakealarm /var/lib/vmbox-wake/armed'

uefi=()
keep=0
pass=0
fail=0

step() { printf '\n\033[0;34m=== %s\033[0m\n' "$*"; }
check() {
    local label="$1"; shift
    if "$@"; then
        printf '\033[0;32m  PASS\033[0m %s\n' "$label"; pass=$(( pass + 1 ))
    else
        printf '\033[0;31m  FAIL\033[0m %s\n' "$label"; fail=$(( fail + 1 ))
    fi
}
guest() { "$VM_CLI" ssh "$VM" "$@" </dev/null 2>/dev/null; }
# Not via `vm ssh`: it boots a stopped sandbox, which once turned a guest that
# had been reset into a "still up" PASS.
# Capture first: `list | grep -q` under pipefail fails on the SIGPIPE grep -q
# causes by exiting early, i.e. exactly when the VM IS running.
running() { local l; l="$("$VM_CLI" list)"; grep -qE "^$VM +running" <<< "$l"; }
stopped() { ! running; }
readonly EVENTS="$HOME/.local/share/vmbox/vms/$VM/events.jsonl"
kv() { sed -n "s/^RTCWAKE $1=//p" <<< "$2" | tail -1; }
probe_line() { guest "grep '^$1 ' /var/lib/vmbox-wake/log | tail -1"; }

# vm wake, keeping both its output and its exit code.
wake() {
    local out rc=0
    out="$("$VM_CLI" wake "$VM" "$@" 2>&1)" || rc=$?
    printf '%s\n' "$out" | grep -E '^RTCWAKE|WAKE:|NO WAKE' >&2
    printf '%s\nRTCWAKE exit=%s\n' "$out" "$rc"
}

setup() {
    step "Setup: fresh sandbox '$VM' ${uefi[*]:-(bios)}, VMBOX_MEM=$VMBOX_MEM"
    "$VM_CLI" rm "$VM" >/dev/null 2>&1 || true
    "$VM_CLI" new "$VM" "${uefi[@]}"
    "$VM_CLI" hibernate-setup "$VM"
    "$VM_CLI" scp "$VM" "$VMBOX_ROOT/tests/rtcwake_guest_probe.sh" "$PROBE" >/dev/null
    guest "sudo bash $PROBE install && sudo install -d /var/lib/vmbox-wake" >/dev/null
}

case_poweroff() {
    step "A. poweroff -> harness powers on at the armed instant (x$ACCEL_POWEROFF)"
    local before out armed boot_epoch boot_id
    before="$(guest 'cat /proc/sys/kernel/random/boot_id')"
    out="$(wake --accel "$ACCEL_POWEROFF" -- "$ARM && sudo systemctl poweroff")"
    armed="$(kv armed_epoch "$out")"
    check "harness exit 0, result=woke" test "$(kv exit "$out")/$(kv result "$out")" = 0/woke
    check "stop classified as poweroff" test "$(kv down "$out")" = poweroff
    check "CMOS alarm == guest wakealarm ($armed)" \
        test "$armed" = "$(guest 'cat /var/lib/vmbox-wake/armed')"
    read -r _ boot_epoch boot_id <<< "$(probe_line boot)"
    check "boot unit ran at $boot_epoch >= armed $armed" test "${boot_epoch:-0}" -ge "${armed:-1}"
    check "it was a fresh boot (boot_id changed)" test "${boot_id:-}" != "$before"
}

case_hibernate() {
    step "B. hibernate -> harness resumes at the armed instant (x$ACCEL_HIBERNATE)"
    local before pid out armed res_epoch res_id
    before="$(guest 'cat /proc/sys/kernel/random/boot_id')"
    guest "setsid -f sh -c 'echo \$\$ > /var/tmp/sleeper.pid; exec sleep 31536000' >/dev/null 2>&1 </dev/null"
    sleep 1
    pid="$(guest 'cat /var/tmp/sleeper.pid')"
    out="$(wake --accel "$ACCEL_HIBERNATE" -- "$ARM && sudo systemctl hibernate")"
    armed="$(kv armed_epoch "$out")"
    check "harness exit 0, result=woke" test "$(kv exit "$out")/$(kv result "$out")" = 0/woke
    check "stop classified as hibernate (QMP SUSPEND_DISK)" test "$(kv down "$out")" = hibernate
    check "CMOS alarm == guest wakealarm ($armed)" \
        test "$armed" = "$(guest 'cat /var/lib/vmbox-wake/armed')"
    check "resumed, not rebooted (boot_id unchanged)" \
        test "$(guest 'cat /proc/sys/kernel/random/boot_id')" = "$before"
    check "pre-hibernate sleep (pid $pid) still alive" \
        guest "tr '\\0' ' ' < /proc/$pid/cmdline | grep -q '^sleep 31536000'"
    read -r _ res_epoch res_id <<< "$(probe_line resume-hibernate)"
    check "resume hook ran at $res_epoch >= armed $armed" test "${res_epoch:-0}" -ge "${armed:-1}"
    check "resume hook ran in the same boot" test "${res_id:-}" = "$before"
    # Unmasked, the ICH9 TCO watchdog reset every resumed guest ~20 s in (see
    # DOCS-rtc-wake.md). A resume that dies a minute in is not a resume.
    local launches
    launches="$(grep -c _RECORDER_READY "$EVENTS")"
    sleep 45
    check "still running 45 s after resume" running
    check "never relaunched (still $launches launches)" \
        test "$(grep -c _RECORDER_READY "$EVENTS")" = "$launches"
    local now_id
    now_id="$(running && guest 'cat /proc/sys/kernel/random/boot_id' || echo not-running)"
    check "...and still the same boot ($now_id)" test "$now_id" = "$before"
    # The X session is dead after a resume (virtio-gpu, see DOCS); `vm run`
    # must still return rather than hang on it.
    check "vm run still returns after resume" timeout 60 "$VM_CLI" run "$VM" true
    printf '  info: WATCHDOG expiries in the log (ignored by vm wake): %s\n' \
        "$(grep -c '"WATCHDOG"' "$EVENTS" || true)"
}

case_not_armed() {
    step "C. negative control: alarm disabled before poweroff -> must stay off"
    local out
    out="$(wake --accel 10 -- "$ARM && sudo rtcwake -m disable >/dev/null && sudo systemctl poweroff")"
    check "harness exit 9, result=not-armed" test "$(kv exit "$out")/$(kv result "$out")" = 9/not-armed
    check "AIE reported off" test "$(kv aie "$out")" = false
    check "machine left powered off" stopped
}

main() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --uefi) uefi=(--uefi); shift ;;
            --keep) keep=1; shift ;;
            *) echo "usage: $0 [--uefi] [--keep]" >&2; exit 2 ;;
        esac
    done
    setup
    case_poweroff
    case_hibernate
    case_not_armed
    (( keep )) || "$VM_CLI" rm "$VM" >/dev/null
    printf '\n\033[0;34m=== RESULT: %d passed, %d failed\033[0m\n' "$pass" "$fail"
    (( fail == 0 ))
}

main "$@"
