#!/bin/bash
# ============================================================================
# vmbox: run a command in a sandbox and report what happened to the machine.
#
# The hard case is a command that powers the guest off (the whole point of the
# tool). ssh cannot report that: the connection dies with the machine and
# returns 255, the same value it returns for a crash or a dropped link. So the
# exit code is written to disk INSIDE the guest, and recovered afterwards from
# the overlay -- which survives the poweroff -- while the verdict comes from
# host-side QMP/serial evidence.
# ============================================================================

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/launch.sh"
source "$(dirname "${BASH_SOURCE[0]}")/ssh.sh"
source "$(dirname "${BASH_SOURCE[0]}")/verdict.sh"

readonly RC_PATH="/var/tmp/vmbox.rc"
# Transport for guest commands. Serial is the default for shutdown work: it
# keeps printing through the poweroff that kills ssh, and it still works when
# sshd does not. ssh stays available as the faster path for bulk work.
readonly VMBOX_TRANSPORT="${VMBOX_TRANSPORT:-auto}"
readonly VMBOX_RUN_TIMEOUT="${VMBOX_RUN_TIMEOUT:-600}"

run_in_vm() {
    local name
    name="$(validate_vm_name "${1:-}")"; shift || true
    require_vm "$name"
    [[ $# -gt 0 ]] || die "usage: vm run <name> <command...>"

    local serial_n serial events
    if vm_is_running "$name"; then
        serial_n="$(( $(vm_next_serial "$name") - 1 ))"
        (( serial_n < 0 )) && serial_n=0
    else
        serial_n="$(launch_vm "$name")"
        vm_wait_ssh "$name" 150 || die "sandbox '$name' did not become reachable"
    fi
    serial="$(vm_serial "$name" "$serial_n")"
    events="$(vm_events "$name")"

    # Record where the verdict should start reading, so a previous boot's
    # shutdown event is never mistaken for this run's outcome.
    local events_before=0
    [[ -f "$events" ]] && events_before=$(wc -l < "$events")

    log "Running in '$name': $*"
    # `|| ssh_rc=$?` is load-bearing: under `set -e` a bare call would abort
    # the script when ssh returns 255 -- which is precisely what a SUCCESSFUL
    # guest poweroff causes. The verdict would then never be printed for the
    # one case this tool exists to report on.
    local ssh_rc=0
    _run_exec "$name" "$@" || ssh_rc=$?

    _run_settle "$name" "$serial" || true
    local frc=0
    _run_finish "$name" "$serial" "$events" "$events_before" "$ssh_rc" || frc=$?
    return "$frc"
}

# stdin is closed: several target installers prompt, and an inherited terminal
# would make them block forever instead of taking their default.
_run_exec() {
    local name="$1"; shift
    local cmd="$*"
    case "$(_run_transport "$name")" in
        serial) _run_exec_serial "$name" "$cmd" ;;
        *)      vm_ssh_exec "$name" \
                    "sh -c '{ $cmd; } ; echo \$? | sudo tee $RC_PATH >/dev/null' </dev/null" \
                    </dev/null ;;
    esac
}

# Prefer ssh when it answers (faster, cleaner), else drive the serial console.
_run_transport() {
    local name="$1"
    case "$VMBOX_TRANSPORT" in
        ssh|serial) printf '%s' "$VMBOX_TRANSPORT"; return ;;
    esac
    if vm_ssh_exec "$name" -o BatchMode=yes -o ConnectTimeout=4 true 2>/dev/null; then
        printf 'ssh'
    else
        printf 'serial'
    fi
}

_run_exec_serial() {
    local name="$1" cmd="$2" console
    console="$(vm_console "$name")"
    [[ -S "$console" ]] || die "no serial console socket for '$name'"
    python3 "$VMBOX_LIB_DIR/serial_exec.py" "$console" \
        "{ $cmd ; } ; echo \$? > $RC_PATH"
}

# Give a guest that is shutting down time to finish writing its serial log.
_run_settle() {
    local name="$1" serial="$2" waited=0
    while vm_is_running "$name" && (( waited < 30 )); do
        grep -qa "$POWEROFF_MARKER" "$serial" 2>/dev/null && break
        sleep 1; waited=$(( waited + 1 ))
    done
    # Let qemu actually exit after the marker appears.
    waited=0
    while vm_is_running "$name" && (( waited < 15 )); do
        grep -qa "$POWEROFF_MARKER" "$serial" 2>/dev/null || break
        sleep 1; waited=$(( waited + 1 ))
    done
}

_run_finish() {
    local name="$1" serial="$2" events="$3" events_before="$4" ssh_rc="$5"

    # Only consider events produced by THIS run.
    local scoped="$events.scoped"
    if [[ -f "$events" ]]; then
        tail -n +$(( events_before + 1 )) "$events" > "$scoped" 2>/dev/null || : > "$scoped"
    else
        : > "$scoped"
    fi

    echo
    local vrc=0
    verdict_report "$name" "$serial" "$scoped" || vrc=$?
    rm -f "$scoped"

    # If the guest stopped, recover the real exit code from the overlay.
    if ! vm_is_running "$name"; then
        local rc
        rc="$(_run_recover_rc "$name")"
        if [[ -n "$rc" ]]; then
            log "command exit code (recovered from the stopped guest): $rc"
            return "$rc"
        fi
        log "no exit code recorded (the command never returned before the machine stopped)"
        return "$vrc"
    fi

    if (( ssh_rc == 255 )); then
        warn "ssh reported 255 but the guest is still running -- connection issue, not a shutdown"
    fi
    return "$ssh_rc"
}

# Boot the sandbox again just far enough to read the recorded exit code.
# The overlay survives the poweroff, so the value written before the machine
# stopped is still there.
_run_recover_rc() {
    local name="$1" rc="" console
    launch_vm "$name" >/dev/null 2>&1 || return 0

    if vm_wait_ssh "$name" 90; then
        rc="$(vm_ssh_exec "$name" "cat $RC_PATH 2>/dev/null" 2>/dev/null | tr -dc '0-9')"
    else
        # ssh may be broken or simply slower than the console; the serial
        # shell can read the file just as well.
        console="$(vm_console "$name")"
        if [[ -S "$console" ]]; then
            rc="$(python3 "$VMBOX_LIB_DIR/serial_exec.py" "$console" \
                    "cat $RC_PATH 2>/dev/null" 2>/dev/null | grep -oE '^[0-9]+' | head -1)"
        fi
    fi
    printf '%s' "$rc"
}
