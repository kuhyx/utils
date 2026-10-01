#!/usr/bin/env bats
# ============================================================================
# vmbox: host-side unit tests for UEFI mode and RTC wake emulation.
#
# No guest is booted: the CMOS decoder is fed register values (the BCD case
# is the exact set read from a real guest on 2026-10-01), and firmware
# selection runs against fake OVMF files. The booting proof is
# tests/rtcwake_e2e.sh. VMBOX_HOME is a per-test temp dir, as in
# test_vmbox.bats -- nothing here may touch ~/.local/share/vmbox.
# ============================================================================

setup() {
    VMBOX_TEST_HOME="$(mktemp -d)"
    export VMBOX_HOME="$VMBOX_TEST_HOME"
    REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/.." && pwd -P)"
    export REPO_ROOT
    source "$REPO_ROOT/lib/common.sh"
    source "$REPO_ROOT/lib/verdict.sh"
    source "$REPO_ROOT/lib/firmware.sh"
    install -d "$VMBOX_VMS_DIR"
}

teardown() {
    [[ -n "${VMBOX_TEST_HOME:-}" && -d "$VMBOX_TEST_HOME" ]] && rm -rf "$VMBOX_TEST_HOME"
}

decode() { python3 "$REPO_ROOT/lib/rtc_alarm.py" decode "$@"; }
field() { jq -r ".$1" <<< "$output"; }

# 2026-10-01T09:01:53Z, the RTC value read from the live guest.
NOW=1790845313

# ---------------------------------------------------------------------------
# CMOS alarm decoding
# ---------------------------------------------------------------------------

@test "decode: BCD 24h registers from a real guest give rtcwake's exact epoch" {
    run decode "$NOW" 0x33 0x02 0x09 0x22 0x0520
    [ "$status" -eq 0 ]
    [ "$(field alarm_epoch)" = 1790845353 ]   # what `rtcwake -s 60` printed
    [ "$(field armed)" = true ]
    [ "$(field rtc_en)" = true ]
    [ "$(field lead_s)" = 40 ]
}

@test "decode: alarm interrupt off means NOT armed, even with valid registers" {
    run decode "$NOW" 0x33 0x02 0x09 0x02
    [ "$(field armed)" = false ]
    [ "$(field aie)" = false ]
    [ "$(field rtc_en)" = null ]
}

@test "decode: binary mode (REG_B DM bit) is not read as BCD" {
    run decode "$NOW" 51 2 9 0x26
    [ "$(field alarm)" = 2026-10-01T09:02:51 ]
}

@test "decode: 12-hour mode maps PM, 12 AM and 12 PM correctly" {
    run decode "$NOW" 0x00 0x00 0x89 0x20
    [ "$(field alarm)" = 2026-10-01T21:00:00 ]
    run decode "$NOW" 0x00 0x00 0x12 0x20
    [ "$(field alarm)" = 2026-10-02T00:00:00 ]
    run decode "$NOW" 0x00 0x00 0x92 0x20
    [ "$(field alarm)" = 2026-10-01T12:00:00 ]
}

@test "decode: an alarm just past midnight wraps to the next day" {
    run decode 1790899190 0x10 0x00 0x00 0x22   # now 23:59:50
    [ "$(field alarm)" = 2026-10-02T00:00:10 ]
    [ "$(field lead_s)" = 20 ]
}

@test "decode: an alarm already in the past is ~24h away, like the hardware" {
    run decode "$NOW" 0x00 0x00 0x09 0x22   # 09:00:00, now 09:01:53
    [ "$(field alarm)" = 2026-10-02T09:00:00 ]
    [ "$(field lead_s)" -gt 86000 ]
}

@test "decode: don't-care bytes (0xC0+) match any value" {
    run decode "$NOW" 0xff 0xff 0xff 0x22
    [ "$(field lead_s)" = 0 ]
}

@test "decode: impossible register values are not armed" {
    run decode "$NOW" 0x75 0x02 0x09 0x22   # second 75
    [ "$(field alarm)" = null ]
    [ "$(field armed)" = false ]
}

@test "rtc_alarm: refuses unknown actions" {
    run python3 "$REPO_ROOT/lib/rtc_alarm.py" poke /nonexistent
    [ "$status" -eq 2 ]
}

# ---------------------------------------------------------------------------
# hibernate classification
# ---------------------------------------------------------------------------

@test "last_event: SUSPEND_DISK then SHUTDOWN is a hibernate" {
    printf '%s\n' '{"event":"SUSPEND_DISK"}' \
        '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-shutdown"}}' > "$VMBOX_HOME/e"
    run verdict_last_event "$VMBOX_HOME/e"
    [ "$output" = hibernate ]
}

@test "last_event: a later plain poweroff is not a hibernate" {
    printf '%s\n' '{"event":"SUSPEND_DISK"}' \
        '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-shutdown"}}' \
        '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-shutdown"}}' > "$VMBOX_HOME/e"
    run verdict_last_event "$VMBOX_HOME/e"
    [ "$output" = guest-shutdown ]
}

@test "verdict: a hibernate is exit 8, not a DIRTY shutdown" {
    install -d "$(vm_dir v)"
    printf '%s\n' '{"event":"SUSPEND_DISK"}' \
        '{"event":"SHUTDOWN","data":{"guest":true,"reason":"guest-shutdown"}}' > "$VMBOX_HOME/e"
    : > "$VMBOX_HOME/serial.log"
    run verdict_report v "$VMBOX_HOME/serial.log" "$VMBOX_HOME/e"
    [ "$status" -eq 8 ]
    [[ "$output" == *hibernated* ]]
    [[ "$output" != *DIRTY* ]]
}

# ---------------------------------------------------------------------------
# firmware selection
# ---------------------------------------------------------------------------

_fake_ovmf() {
    printf 'code' > "$VMBOX_HOME/CODE.fd"
    printf 'vars-template' > "$VMBOX_HOME/VARS.fd"
    export VMBOX_OVMF_CODE="$VMBOX_HOME/CODE.fd" VMBOX_OVMF_VARS="$VMBOX_HOME/VARS.fd"
}

@test "firmware: default is bios, and bios adds no qemu args" {
    install -d "$(vm_dir v)"
    [ "$(firmware_of v)" = bios ]
    local -a args=()
    firmware_qemu_args v args
    [ "${#args[@]}" -eq 0 ]
}

@test "firmware: meta uefi wins over the default, env wins over meta" {
    install -d "$(vm_dir v)"
    meta_set v firmware uefi
    [ "$(firmware_of v)" = uefi ]
    VMBOX_FIRMWARE=bios run firmware_of v
    [ "$output" = bios ]
}

@test "firmware: an unknown firmware name is refused" {
    install -d "$(vm_dir v)"
    VMBOX_FIRMWARE=coreboot run firmware_of v
    [ "$status" -ne 0 ]
}

@test "firmware: uefi adds read-only code + a per-VM varstore copied from the template" {
    _fake_ovmf
    install -d "$(vm_dir v)"
    meta_set v firmware uefi
    local -a args=()
    firmware_qemu_args v args
    [ "${#args[@]}" -eq 4 ]
    [[ "${args[1]}" == *"unit=0,readonly=on,file=$VMBOX_HOME/CODE.fd" ]]
    [[ "${args[3]}" == *"unit=1,file=$(vm_efivars v)" ]]
    [ "$(cat "$(vm_efivars v)")" = vars-template ]
}

@test "firmware: missing OVMF fails closed instead of booting as bios" {
    install -d "$(vm_dir v)"
    meta_set v firmware uefi
    VMBOX_OVMF_CODE="$VMBOX_HOME/nope.fd" run firmware_qemu_args v args
    [ "$status" -ne 0 ]
    [[ "$output" == *"not readable"* ]]
}

# ---------------------------------------------------------------------------
# vm wake argument handling (no guest needed)
# ---------------------------------------------------------------------------

@test "vm wake: unknown sandbox and bad --accel are refused before anything runs" {
    run "$REPO_ROOT/bin/vm" wake nosuch -- true
    [ "$status" -ne 0 ]
    [[ "$output" == *"no such vm"* ]]
    install -d "$(vm_dir v)"
    run "$REPO_ROOT/bin/vm" wake v --accel 0 -- true
    [ "$status" -ne 0 ]
    [[ "$output" == *"positive integer"* ]]
}
