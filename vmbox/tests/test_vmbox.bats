#!/usr/bin/env bats
# Host-side unit tests for vmbox's pure functions. These deliberately do NOT
# boot a VM: booting is covered by the destructive end-to-end demo in README.
# Everything here runs against a temporary VMBOX_HOME.

setup() {
    VMBOX_TEST_HOME="$(mktemp -d)"
    export VMBOX_HOME="$VMBOX_TEST_HOME"
    REPO="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
    export REPO
    # shellcheck source=../lib/common.sh
    source "$REPO/lib/common.sh"
}

teardown() {
    [[ -n "${VMBOX_TEST_HOME:-}" && -d "$VMBOX_TEST_HOME" ]] && rm -rf "$VMBOX_TEST_HOME"
}

@test "validate_vm_name accepts ordinary names" {
    run validate_vm_name "demo"
    [ "$status" -eq 0 ]
    [ "$output" = "demo" ]
    run validate_vm_name "test-1_x"
    [ "$status" -eq 0 ]
}

@test "validate_vm_name rejects path traversal and spaces" {
    run validate_vm_name "../escape"
    [ "$status" -ne 0 ]
    run validate_vm_name "bad name"
    [ "$status" -ne 0 ]
    run validate_vm_name ""
    [ "$status" -ne 0 ]
}

@test "meta_set overwrites rather than duplicating a key" {
    mkdir -p "$(vm_dir demo)"
    meta_set demo rtc "2026-01-01T00:00:00"
    meta_set demo rtc "2026-08-22T20:55:00"
    run bash -c "grep -c '^rtc=' '$(vm_meta demo)'"
    [ "$output" = "1" ]
    run meta_get demo rtc
    [ "$output" = "2026-08-22T20:55:00" ]
}

@test "vm_next_serial starts at 0 and continues past the highest index" {
    mkdir -p "$(vm_dir demo)"
    run vm_next_serial demo
    [ "$output" = "0" ]
    touch "$(vm_dir demo)/serial.0.log" "$(vm_dir demo)/serial.7.log"
    run vm_next_serial demo
    [ "$output" = "8" ]
}

@test "vm_is_running is false for a stale pidfile" {
    mkdir -p "$(vm_dir demo)"
    echo "999999" > "$(vm_pidfile demo)"
    run vm_is_running demo
    [ "$status" -ne 0 ]
}

@test "verdict classifies a guest poweroff as clean only with the serial marker" {
    source "$REPO/lib/verdict.sh"
    mkdir -p "$(vm_dir demo)"
    local ev="$(vm_dir demo)/events.jsonl"
    printf '%s\n' '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-shutdown"}}' > "$ev"

    run verdict_last_event "$ev"
    [ "$output" = "guest-shutdown" ]

    # Truncated serial log -> the machine stopped, but not cleanly.
    local ser="$(vm_dir demo)/serial.0.log"
    printf 'Stopping some unit...\n' > "$ser"
    run verdict_serial_complete "$ser"
    [ "$status" -ne 0 ]

    printf 'reboot: Power down\n' >> "$ser"
    run verdict_serial_complete "$ser"
    [ "$status" -eq 0 ]
}

@test "verdict distinguishes reset, panic and host-initiated stops" {
    source "$REPO/lib/verdict.sh"
    mkdir -p "$(vm_dir demo)"
    local ev="$(vm_dir demo)/events.jsonl"

    printf '%s\n' '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-reset"}}' > "$ev"
    run verdict_last_event "$ev"
    [ "$output" = "guest-reset" ]

    printf '%s\n' '{"event":"GUEST_PANICKED","data":{}}' > "$ev"
    run verdict_last_event "$ev"
    [ "$output" = "panic" ]

    printf '%s\n' '{"event":"SHUTDOWN","data":{"guest":false,"reason":"host-qmp-quit"}}' > "$ev"
    run verdict_last_event "$ev"
    [ "$output" = "host-qmp-quit" ]

    : > "$ev"
    run verdict_last_event "$ev"
    [ "$output" = "none" ]
}

@test "verdict reads the LAST event, so an earlier boot does not win" {
    source "$REPO/lib/verdict.sh"
    mkdir -p "$(vm_dir demo)"
    local ev="$(vm_dir demo)/events.jsonl"
    {
        printf '%s\n' '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-reset"}}'
        printf '%s\n' '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-shutdown"}}'
    } > "$ev"
    run verdict_last_event "$ev"
    [ "$output" = "guest-shutdown" ]
}
