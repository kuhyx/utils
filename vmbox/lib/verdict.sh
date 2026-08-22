#!/bin/bash
# ============================================================================
# vmbox: classify what happened to a guest, from the HOST.
#
# A guest cannot report its own poweroff: the connection carrying the report
# dies with it, and ssh returns 255 for a clean shutdown, a crash, a killed
# sshd and a network blip alike. So the verdict is read from two host-side
# artefacts that outlive the VM -- the QMP event log and the serial log.
# ============================================================================

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# The line the kernel prints as the very last thing on a complete poweroff.
readonly POWEROFF_MARKER='reboot: Power down'

# Read the last SHUTDOWN/panic event out of events.jsonl.
# Echoes one of: guest-shutdown | guest-reset | host-* | panic | none
verdict_last_event() {
    local events="$1"
    [[ -s "$events" ]] || { printf 'none'; return 0; }
    python3 - "$events" <<'PY'
import json, sys

kind = "none"
with open(sys.argv[1], encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        event = msg.get("event", "")
        if event == "GUEST_PANICKED":
            kind = "panic"
        elif event == "SHUTDOWN":
            data = msg.get("data", {})
            reason = data.get("reason", "")
            # `guest` distinguishes a guest-initiated stop from one we caused.
            kind = reason if reason else ("guest-shutdown" if data.get("guest") else "host")
print(kind)
PY
}

# Did the guest reach the end of its shutdown sequence, or die partway?
# This is what separates "shut down" from "shut down COMPLETELY".
verdict_serial_complete() {
    local serial="$1"
    [[ -s "$serial" ]] || return 1
    grep -qa "$POWEROFF_MARKER" "$serial"
}

# Liveness probe, so a merely SLOW script (an installer running pacman -Syu)
# is not reported as hung.
verdict_is_alive() {
    local name="$1" serial="$2" before after
    vm_is_running "$name" || return 1
    before=$(stat -c %s "$serial" 2>/dev/null || echo 0)
    sleep 3
    after=$(stat -c %s "$serial" 2>/dev/null || echo 0)
    [[ "$after" != "$before" ]] && return 0
    source "$VMBOX_LIB_DIR/ssh.sh"
    vm_ssh_exec "$name" -o BatchMode=yes -o ConnectTimeout=3 true 2>/dev/null
}

# Print the human-readable verdict and return a distinct exit code per outcome:
#   0 clean poweroff   3 dirty   4 rebooted   5 panicked   6 hung   7 still running
verdict_report() {
    local name="$1" serial="$2" events="$3" kind
    kind="$(verdict_last_event "$events")"

    case "$kind" in
        guest-shutdown)
            if verdict_serial_complete "$serial"; then
                ok "VERDICT: clean poweroff -- guest powered itself off and reached '$POWEROFF_MARKER'"
                return 0
            fi
            warn "VERDICT: DIRTY shutdown -- the VM stopped, but the serial log never reached"
            warn "         '$POWEROFF_MARKER'; the sequence was cut short (see $serial)"
            return 3
            ;;
        guest-reset)
            warn "VERDICT: REBOOTED, did not power off -- the guest reset instead of halting"
            return 4
            ;;
        panic)
            warn "VERDICT: KERNEL PANIC -- the guest crashed rather than shutting down"
            return 5
            ;;
        host*|none)
            if vm_is_running "$name"; then
                ok "VERDICT: still running (no shutdown event)"
                return 7
            fi
            warn "VERDICT: stopped without a guest shutdown event (host-initiated or killed)"
            return 6
            ;;
        *)
            warn "VERDICT: unrecognised shutdown reason '$kind'"
            return 6
            ;;
    esac
}
