#!/usr/bin/env bats
# ============================================================================
# vmbox: host-side unit tests.
#
# Scope, deliberately: everything that can be decided WITHOUT booting a guest --
# name validation, meta handling, serial rotation and the VM path helpers.
# Booting is covered by tests/destructive_demo.sh, which is slow and needs a
# built base image; these run in well under a second and gate every commit.
#
# The verdict table lives in test_verdict.bats and the hardware shim in
# test_shim.bats; the shared fixture (temp VMBOX_HOME) is test_helper.bash.
# ============================================================================

load test_helper

# ---------------------------------------------------------------------------
# name validation
# ---------------------------------------------------------------------------

@test "validate_vm_name accepts ordinary names" {
    run validate_vm_name "demo"
    [ "$status" -eq 0 ]
    [ "$output" = "demo" ]
}

@test "validate_vm_name accepts digits, dashes and underscores" {
    run validate_vm_name "t1_test-2"
    [ "$status" -eq 0 ]
    [ "$output" = "t1_test-2" ]
}

@test "validate_vm_name rejects an empty name" {
    run validate_vm_name ""
    [ "$status" -ne 0 ]
}

@test "validate_vm_name rejects path traversal" {
    # A name becomes a directory under VMBOX_VMS_DIR, so a slash or a ".."
    # would let `vm rm` delete outside the state dir.
    run validate_vm_name "../escape"
    [ "$status" -ne 0 ]
    run validate_vm_name "a/b"
    [ "$status" -ne 0 ]
}

@test "validate_vm_name rejects a leading dash" {
    # Would be parsed as an option by qemu -name and by the CLI itself.
    run validate_vm_name "-rf"
    [ "$status" -ne 0 ]
}

@test "validate_vm_name rejects shell metacharacters" {
    run validate_vm_name 'a;rm -rf /'
    [ "$status" -ne 0 ]
    run validate_vm_name 'a$(id)'
    [ "$status" -ne 0 ]
}

@test "validate_vm_name enforces the 32-character cap" {
    run validate_vm_name "$(printf 'a%.0s' {1..32})"
    [ "$status" -eq 0 ]
    run validate_vm_name "$(printf 'a%.0s' {1..33})"
    [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# meta handling
# ---------------------------------------------------------------------------

@test "meta_set then meta_get round-trips a value" {
    _fake_vm m1
    meta_set m1 ssh_port 2301
    run meta_get m1 ssh_port
    [ "$status" -eq 0 ]
    [ "$output" = "2301" ]
}

@test "meta_set overwrites rather than appending a duplicate key" {
    _fake_vm m2
    meta_set m2 rtc "2026-01-01T00:00:00"
    meta_set m2 rtc "2026-08-22T20:55:00"
    run meta_get m2 rtc
    [ "$output" = "2026-08-22T20:55:00" ]
    # Exactly one rtc line, or meta_get would silently return the stale first.
    run grep -c '^rtc=' "$(vm_meta m2)"
    [ "$output" = "1" ]
}

@test "meta_set keeps unrelated keys intact" {
    _fake_vm m3
    meta_set m3 index 1
    meta_set m3 ssh_port 2301
    meta_set m3 index 2
    run meta_get m3 ssh_port
    [ "$output" = "2301" ]
    run meta_get m3 index
    [ "$output" = "2" ]
}

@test "meta_get fails for a missing key" {
    _fake_vm m4
    meta_set m4 index 1
    run meta_get m4 nosuchkey
    [ "$status" -ne 0 ]
}

@test "meta_get fails for a vm with no meta file at all" {
    _fake_vm m5
    run meta_get m5 index
    [ "$status" -ne 0 ]
}

@test "meta_get returns a value containing '=' unmangled" {
    # meta is key=value; the value itself may legitimately contain '='.
    _fake_vm m6
    meta_set m6 opts "a=b=c"
    run meta_get m6 opts
    [ "$output" = "a=b=c" ]
}

@test "meta_set refuses a multi-line value" {
    # A newline would forge an extra key on the next meta_get.
    _fake_vm m7
    run meta_set m7 rtc "$(printf 'a\nindex=99')"
    [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# serial rotation
# ---------------------------------------------------------------------------

@test "vm_next_serial starts at 0 for a fresh vm" {
    _fake_vm s1
    run vm_next_serial s1
    [ "$output" = "0" ]
}

@test "vm_next_serial increments past the highest existing log" {
    _fake_vm s2
    touch "$(vm_serial s2 0)" "$(vm_serial s2 1)"
    run vm_next_serial s2
    [ "$output" = "2" ]
}

@test "vm_next_serial does not reuse a number when logs are sparse" {
    # A relaunch must never overwrite the log a verdict is about to be read
    # from, so the counter tracks the MAXIMUM, not the count.
    _fake_vm s3
    touch "$(vm_serial s3 0)" "$(vm_serial s3 7)"
    run vm_next_serial s3
    [ "$output" = "8" ]
}

@test "vm_next_serial ignores non-numeric serial files" {
    _fake_vm s4
    touch "$(vm_serial s4 0)"
    touch "$(vm_dir s4)/serial.old.log"
    run vm_next_serial s4
    [ "$output" = "1" ]
}

@test "vm_next_serial ignores the qemu-stderr sidecar" {
    # launch.sh writes serial.N.log.qemu-stderr next to the log; parsing it as
    # a serial number would inflate the counter forever.
    _fake_vm s5
    touch "$(vm_serial s5 0)" "$(vm_serial s5 0).qemu-stderr"
    run vm_next_serial s5
    [ "$output" = "1" ]
}

# ---------------------------------------------------------------------------
# path helpers
# ---------------------------------------------------------------------------

@test "vm state paths all live under VMBOX_HOME" {
    # The whole point of the temp-dir redirect: no helper may escape it.
    for p in "$(vm_dir p1)" "$(vm_overlay p1)" "$(vm_meta p1)" \
             "$(vm_qmp_sock p1)" "$(vm_console p1)" "$(vm_events p1)" \
             "$(vm_pidfile p1)" "$(vm_serial p1 0)"; do
        [[ "$p" == "$VMBOX_HOME"/* ]] || {
            echo "escaped VMBOX_HOME: $p"
            return 1
        }
    done
}

@test "vm_exists and require_vm agree" {
    run vm_exists nope
    [ "$status" -ne 0 ]
    run require_vm nope
    [ "$status" -ne 0 ]
    _fake_vm yes1
    run vm_exists yes1
    [ "$status" -eq 0 ]
    run require_vm yes1
    [ "$status" -eq 0 ]
}
