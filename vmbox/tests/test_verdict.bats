#!/usr/bin/env bats
# ============================================================================
# vmbox: host-side unit tests for the shutdown verdict.
#
# Event parsing, serial completeness and the full exit-code table, all decided
# from fake event logs and serial text -- no guest is booted. Fixture (temp
# VMBOX_HOME, _fake_vm) is test_helper.bash.
# ============================================================================

load test_helper

# ---------------------------------------------------------------------------
# verdict: event parsing
# ---------------------------------------------------------------------------

@test "verdict_last_event reports none for a missing or empty log" {
    run verdict_last_event "$VMBOX_HOME/nosuch.jsonl"
    [ "$output" = "none" ]
    : > "$VMBOX_HOME/empty.jsonl"
    run verdict_last_event "$VMBOX_HOME/empty.jsonl"
    [ "$output" = "none" ]
}

@test "verdict_last_event reads a guest-initiated poweroff" {
    printf '%s\n' \
        '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-shutdown"}}' \
        > "$VMBOX_HOME/e.jsonl"
    run verdict_last_event "$VMBOX_HOME/e.jsonl"
    [ "$output" = "guest-shutdown" ]
}

@test "verdict_last_event distinguishes a reset from a poweroff" {
    printf '%s\n' \
        '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-reset"}}' \
        > "$VMBOX_HOME/e.jsonl"
    run verdict_last_event "$VMBOX_HOME/e.jsonl"
    [ "$output" = "guest-reset" ]
}

@test "verdict_last_event reports a panic" {
    printf '%s\n' '{"event":"GUEST_PANICKED","data":{"action":"pause"}}' \
        > "$VMBOX_HOME/e.jsonl"
    run verdict_last_event "$VMBOX_HOME/e.jsonl"
    [ "$output" = "panic" ]
}

@test "verdict_last_event takes the LAST event, not the first" {
    # events.jsonl is append-only across boots, so an old poweroff must never
    # be mistaken for the current run's outcome.
    printf '%s\n' \
        '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-shutdown"}}' \
        '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-reset"}}' \
        > "$VMBOX_HOME/e.jsonl"
    run verdict_last_event "$VMBOX_HOME/e.jsonl"
    [ "$output" = "guest-reset" ]
}

@test "verdict_last_event skips malformed lines instead of dying" {
    # A truncated final line is normal: the recorder is killed with the VM.
    printf '%s\n' \
        'not json at all' \
        '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-shutdown"}}' \
        '{"event":"SHUT' \
        > "$VMBOX_HOME/e.jsonl"
    run verdict_last_event "$VMBOX_HOME/e.jsonl"
    [ "$status" -eq 0 ]
    [ "$output" = "guest-shutdown" ]
}

@test "verdict_last_event ignores POWERDOWN, which proves nothing" {
    # POWERDOWN means the ACPI request was DELIVERED. With no OS booted, qemu
    # emits it and then runs forever -- treating it as a stop is a false pass.
    printf '%s\n' '{"event":"POWERDOWN"}' > "$VMBOX_HOME/e.jsonl"
    run verdict_last_event "$VMBOX_HOME/e.jsonl"
    [ "$output" = "none" ]
}

@test "verdict_last_event marks a host-initiated stop as host" {
    printf '%s\n' '{"event":"SHUTDOWN","data":{"guest":false}}' \
        > "$VMBOX_HOME/e.jsonl"
    run verdict_last_event "$VMBOX_HOME/e.jsonl"
    [ "$output" = "host" ]
}

# ---------------------------------------------------------------------------
# verdict: serial completeness
# ---------------------------------------------------------------------------

@test "verdict_serial_complete requires the kernel's final power-down line" {
    printf 'Reached target System Power Off.\n' > "$VMBOX_HOME/s.log"
    run verdict_serial_complete "$VMBOX_HOME/s.log"
    [ "$status" -ne 0 ]

    printf 'Reached target System Power Off.\n[   85.5] reboot: Power down\n' \
        > "$VMBOX_HOME/s.log"
    run verdict_serial_complete "$VMBOX_HOME/s.log"
    [ "$status" -eq 0 ]
}

@test "verdict_serial_complete fails on an empty or missing log" {
    : > "$VMBOX_HOME/s.log"
    run verdict_serial_complete "$VMBOX_HOME/s.log"
    [ "$status" -ne 0 ]
    run verdict_serial_complete "$VMBOX_HOME/nosuch.log"
    [ "$status" -ne 0 ]
}

@test "verdict_serial_complete matches despite ANSI escapes in the log" {
    # The serial log is a raw console capture, full of colour codes; grep -a
    # is what keeps it readable as text.
    printf '\033[0;32m OK \033[0m[   85.5] reboot: Power down\n' \
        > "$VMBOX_HOME/s.log"
    run verdict_serial_complete "$VMBOX_HOME/s.log"
    [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# verdict: the full table, exit code by exit code
# ---------------------------------------------------------------------------

_verdict_case() {
    # _verdict_case <events-json-line|""> <serial-text> -> sets $status
    local name="v1"
    _fake_vm "$name"
    local events serial
    events="$(vm_events "$name")"
    serial="$(vm_serial "$name" 0)"
    if [[ -n "$1" ]]; then printf '%s\n' "$1" > "$events"; else : > "$events"; fi
    printf '%s' "$2" > "$serial"
    verdict_report "$name" "$serial" "$events"
}

@test "verdict: clean poweroff exits 0" {
    run _verdict_case \
        '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-shutdown"}}' \
        'reboot: Power down'
    [ "$status" -eq 0 ]
    [[ "$output" == *"clean poweroff"* ]]
}

@test "verdict: a stop that never reached the marker is DIRTY, exit 3" {
    # This is the discriminator the whole design turns on: guest:true alone
    # does NOT prove the machine shut down completely.
    run _verdict_case \
        '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-shutdown"}}' \
        'Stopping session... (log ends here)'
    [ "$status" -eq 3 ]
    [[ "$output" == *"DIRTY"* ]]
}

@test "verdict: a reboot is exit 4, not a poweroff" {
    run _verdict_case \
        '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-reset"}}' \
        ''
    [ "$status" -eq 4 ]
    [[ "$output" == *"REBOOTED"* ]]
}

@test "verdict: a kernel panic is exit 5" {
    run _verdict_case '{"event":"GUEST_PANICKED","data":{"action":"pause"}}' ''
    [ "$status" -eq 5 ]
    [[ "$output" == *"PANIC"* ]]
}

@test "verdict: no event and no live qemu is exit 6" {
    # No pidfile -> vm_is_running is false -> stopped without a guest event.
    run _verdict_case '' ''
    [ "$status" -eq 6 ]
}

@test "verdict: a host-initiated stop is exit 6" {
    run _verdict_case '{"event":"SHUTDOWN","data":{"guest":false}}' ''
    [ "$status" -eq 6 ]
}

@test "verdict: an unrecognised reason is exit 6, never a silent pass" {
    run _verdict_case \
        '{"event":"SHUTDOWN","data":{"guest":true,"reason":"brand-new-reason"}}' \
        ''
    [ "$status" -eq 6 ]
    [[ "$output" == *"unrecognised"* ]]
}
