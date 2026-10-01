#!/bin/bash
# ============================================================================
# vmbox: `vm wake` -- emulate "the PC wakes itself on its RTC alarm".
#
# QEMU does not power a guest on from S5, or resume it from S4, when the CMOS
# alarm fires: measured on qemu 11.1.1 (SeaBIOS and OVMF), the alarm flag in
# register C sets and the machine stays in 'shutdown'. Only S3 wakes natively.
# So the firmware's half is emulated here, and everything around it is real:
#
#   1. QEMU is told to PAUSE instead of exiting when the guest goes down, so
#      the guest's CMOS outlives the poweroff/hibernate the way it does on a
#      real board.
#   2. The armed instant is read from that CMOS over QMP (rtc_alarm.py), not
#      from anything the guest said about itself.
#   3. We wait until the guest RTC reaches it (optionally time-accelerated),
#      then power the machine on with the RTC at that instant -- a cold boot
#      for S5, a resume from the swap image for S4, on identical hardware.
# ============================================================================

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
# shellcheck source=launch.sh
source "$(dirname "${BASH_SOURCE[0]}")/launch.sh"
# shellcheck source=ssh.sh
source "$(dirname "${BASH_SOURCE[0]}")/ssh.sh"

readonly WAKE_DOWN_TIMEOUT="${VMBOX_WAKE_DOWN_TIMEOUT:-240}"
readonly WAKE_UP_TIMEOUT="${VMBOX_WAKE_UP_TIMEOUT:-180}"

# Exit codes, distinct so a test can assert the failure it expects.
readonly WAKE_RC_NOT_ARMED=9 WAKE_RC_NEVER_DOWN=10 WAKE_RC_NOT_BACK=11
readonly WAKE_RC_TOO_LONG=12 WAKE_RC_WRONG_STOP=13 WAKE_RC_CLOCK=14

_wake_qmp()   { python3 "$VMBOX_LIB_DIR/qmp.py" "$(vm_qmp_ctl "$1")" "${@:2}"; }
_wake_alarm() { python3 "$VMBOX_LIB_DIR/rtc_alarm.py" "$1" "$(vm_qmp_ctl "$2")"; }
_wake_kv()    { printf 'RTCWAKE %s=%s\n' "$1" "$2"; }
_wake_utc()   { date -u -d "@$1" +%Y-%m-%dT%H:%M:%S; }

# "mem smp firmware" of the RUNNING qemu. A resume needs the hardware it
# hibernated on -- a different RAM size makes the kernel discard the image --
# so the relaunch replays what was actually used, not today's defaults.
_wake_hw_of_running() {
    local pid i mem="" smp="" fw=bios
    local -a argv=()
    pid="$(cat "$(vm_pidfile "$1")")"
    mapfile -d '' -t argv < "/proc/$pid/cmdline"
    for (( i = 0; i < ${#argv[@]}; i++ )); do
        case "${argv[i]}" in
            -m)        mem="${argv[i + 1]}" ;;
            -smp)      smp="${argv[i + 1]}" ;;
            if=pflash*) fw=uefi ;;
        esac
    done
    printf '%s %s %s' "$mem" "$smp" "$fw"
}

# Poll the event log (past line $2) until the guest stops or panics.
_wake_wait_down() {
    local name="$1" from="$2" events now deadline
    events="$(vm_events "$name")"
    printf -v now '%(%s)T' -1
    deadline=$(( now + WAKE_DOWN_TIMEOUT ))
    while (( now < deadline )); do
        tail -n +"$(( from + 1 ))" "$events" 2>/dev/null |
            grep -qE '"event": "(SHUTDOWN|GUEST_PANICKED)"' && return 0
        vm_is_running "$name" || return 1
        sleep 1
        printf -v now '%(%s)T' -1
    done
    return 1
}

_wake_quit() {
    local name="$1" pid waited=0
    pid="$(cat "$(vm_pidfile "$name")" 2>/dev/null || true)"
    _wake_qmp "$name" quit >/dev/null 2>&1 || true
    while [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && (( waited < 30 )); do
        sleep 1; waited=$(( waited + 1 ))
    done
    vm_is_running "$name" && die "qemu for '$name' did not exit after quit"
    return 0
}

cmd_wake() {
    local name accel=1 max_wait=900
    name="$(validate_vm_name "${1:-}")"; shift || true
    require_vm "$name"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --accel)    accel="${2:-}"; shift 2 ;;
            --max-wait) max_wait="${2:-}"; shift 2 ;;
            --)         shift; break ;;
            *)          break ;;
        esac
    done
    [[ "$accel" =~ ^[1-9][0-9]*$ ]] || die "--accel needs a positive integer"
    [[ "$max_wait" =~ ^[0-9]+$ ]] || die "--max-wait needs seconds"
    [[ $# -gt 0 ]] || die "usage: vm wake <name> [--accel N] [--max-wait S] [--] <guest command...>"
    command -v jq >/dev/null || die "vm wake needs jq -- run: $VMBOX_ROOT/install.sh"

    if ! vm_is_running "$name"; then
        launch_vm "$name" >/dev/null
        vm_wait_ssh "$name" 150 || die "sandbox '$name' did not become reachable"
    fi
    _wake_qmp "$name" pause-on-shutdown >/dev/null || die "could not set shutdown=pause over QMP"

    local events hw before=0 ssh_pid
    events="$(vm_events "$name")"
    [[ -f "$events" ]] && before="$(wc -l < "$events")"
    hw="$(_wake_hw_of_running "$name")"

    log "Running in '$name' (machine will pause, not exit, when it goes down): $*"
    vm_ssh_exec "$name" "$*" </dev/null &
    ssh_pid=$!
    if ! _wake_wait_down "$name" "$before"; then
        kill "$ssh_pid" 2>/dev/null || true
        warn "the guest did not go down within ${WAKE_DOWN_TIMEOUT}s"
        _wake_kv result never-down
        return "$WAKE_RC_NEVER_DOWN"
    fi
    kill "$ssh_pid" 2>/dev/null || true
    wait "$ssh_pid" 2>/dev/null || true

    local scoped="$events.wake" kind
    tail -n +"$(( before + 1 ))" "$events" > "$scoped"
    kind="$(python3 "$VMBOX_LIB_DIR/last_event.py" "$scoped")"
    rm -f "$scoped"
    case "$kind" in
        guest-shutdown) kind=poweroff ;;
        hibernate) ;;
        *) warn "the guest stopped by '$kind', not a poweroff or hibernate"
           # Do not leave it paused in 'shutdown': it would list as running
           # while the guest is down, and the next `vm run` would stall.
           _wake_quit "$name"
           _wake_kv result "wrong-stop:$kind"
           return "$WAKE_RC_WRONG_STOP" ;;
    esac
    _wake_kv down "$kind"
    _wake_after_down "$name" "$accel" "$max_wait" "$hw"
}

_wake_after_down() {
    local name="$1" accel="$2" max_wait="$3" hw="$4" report
    report="$(_wake_alarm read "$name")" || die "could not read the CMOS alarm over QMP"

    local armed alarm_epoch down_epoch lead aie rtc_en regs
    armed="$(jq -r '.armed' <<< "$report")"
    aie="$(jq -r '.aie' <<< "$report")"
    rtc_en="$(jq -r '.rtc_en' <<< "$report")"
    regs="$(jq -c '.regs' <<< "$report")"
    down_epoch="$(jq -r '.rtc_now_epoch' <<< "$report")"
    _wake_kv rtc_at_down "$(_wake_utc "$down_epoch")"
    _wake_kv cmos_regs "$regs"
    _wake_kv aie "$aie"
    _wake_kv rtc_en "$rtc_en"
    if [[ "$armed" != true ]]; then
        warn "NO WAKE ARMED: alarm interrupt disabled in CMOS -- the machine would stay off"
        _wake_quit "$name"
        _wake_kv result not-armed
        return "$WAKE_RC_NOT_ARMED"
    fi
    alarm_epoch="$(jq -r '.alarm_epoch' <<< "$report")"
    lead="$(jq -r '.lead_s' <<< "$report")"
    _wake_kv armed_epoch "$alarm_epoch"
    _wake_kv armed_utc "$(_wake_utc "$alarm_epoch")"
    _wake_kv lead_guest_s "$lead"
    [[ "$rtc_en" == false ]] &&
        warn "PM1_EN.RTC_EN is clear: QEMU does not care, but a real chipset may not wake"

    local real_wait=$(( (lead + accel - 1) / accel ))
    if (( real_wait > max_wait )); then
        warn "alarm is ${lead}s of guest time away (${real_wait}s real at x$accel) > --max-wait $max_wait"
        _wake_quit "$name"
        _wake_kv result too-far
        return "$WAKE_RC_TOO_LONG"
    fi
    log "Machine is off; alarm in ${lead}s guest time -> waiting ${real_wait}s real (x$accel)"
    local t0 t1
    printf -v t0 '%(%s)T' -1
    sleep "$real_wait"
    printf -v t1 '%(%s)T' -1
    _wake_kv accel "$accel"
    _wake_kv waited_real_s "$(( t1 - t0 ))"

    # The firmware wakes the instant the RTC matches; with acceleration the
    # real RTC is still short of that, so power on AT the alarm instant.
    local now_epoch base
    now_epoch="$(_wake_alarm now "$name")"
    base=$(( now_epoch > alarm_epoch ? now_epoch : alarm_epoch ))
    _wake_kv poweron_rtc "$(_wake_utc "$base")"
    _wake_quit "$name"
    _wake_power_on "$name" "$hw" "$base" "$alarm_epoch"
}

_wake_power_on() {
    local name="$1" hw="$2" base="$3" alarm_epoch="$4" mem smp fw t0 t1 guest_now
    read -r mem smp fw <<< "$hw"
    log "Powering '$name' on (RTC $(_wake_utc "$base"), ${mem}M x${smp}, $fw)"
    printf -v t0 '%(%s)T' -1
    # `env`, not a prefix assignment: VMBOX_MEM/SMP are readonly in this
    # shell (launch.sh), and the relaunch must not inherit this shell's values.
    # watchdog=none: QEMU reset every resumed guest ~20 s in. TCO_TMR reads
    # 0x32 (30 s) after a cold boot but 0x04 (2.4 s, QEMU's default) after a
    # resume, and the restored driver keeps pinging every 15 s (measured).
    # An emulator artefact, not the flow under test; the WATCHDOG events
    # still land in events.jsonl.
    if ! env VMBOX_MEM="$mem" VMBOX_SMP="$smp" VMBOX_FIRMWARE="$fw" \
         VMBOX_RTC_ONCE="$(_wake_utc "$base")" VMBOX_START_TIMEOUT="$WAKE_UP_TIMEOUT" \
         VMBOX_WATCHDOG_ACTION=none "$VMBOX_ROOT/bin/vm" start "$name" >/dev/null; then
        warn "the guest did not come back within ${WAKE_UP_TIMEOUT}s"
        _wake_kv result not-back
        return "$WAKE_RC_NOT_BACK"
    fi
    printf -v t1 '%(%s)T' -1
    guest_now="$(vm_ssh_exec "$name" 'date +%s' | tr -dc '0-9')"
    _wake_kv back_after_real_s "$(( t1 - t0 ))"
    _wake_kv guest_clock_at_ssh "$(_wake_utc "$guest_now")"
    _wake_kv up_after_alarm_guest_s "$(( guest_now - alarm_epoch ))"
    # Powered on AT the alarm, so a guest clock behind it means the guest did
    # not take its time from the RTC -- a resume under kvmclock does exactly
    # that, and every time-gated unit would then decide on the wrong time.
    if (( guest_now < alarm_epoch )); then
        warn "guest clock is $(( alarm_epoch - guest_now ))s BEHIND its own alarm: it did not read"
        warn "the RTC (kvmclock?). Run: vm hibernate-setup $name  (adds no-kvmclock)"
        _wake_kv result clock-not-from-rtc
        return "$WAKE_RC_CLOCK"
    fi
    _wake_kv result woke
    ok "WAKE: guest is back $(( guest_now - alarm_epoch ))s (guest clock) after its alarm"
}
