#!/bin/bash
# ============================================================================
# vmbox: sandbox lifecycle -- create, reset, delete.
#
# A sandbox is a thin qcow2 overlay on the sealed base image. Creating one is
# instant and costs ~200 KB; resetting is `rm` + recreate, so it is
# sub-second no matter how thoroughly the guest was destroyed.
# ============================================================================

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# The base must never be written to: qcow2 overlays record their backing file's
# state, so booting the base once silently invalidates EVERY overlay on it.
# chmod 444 is the lock; this hash is what actually detects a breach.
overlay_verify_base() {
    [[ -f "$VMBOX_BASE_IMG" ]] ||
        die "no base image -- build it first with: vm build"
    [[ -f "$VMBOX_BASE_SHA" ]] ||
        die "base image has no checksum sidecar -- rebuild with: vm build --force"

    local expected actual
    expected="$(cat "$VMBOX_BASE_SHA")"
    actual="$(sha256sum "$VMBOX_BASE_IMG" | awk '{print $1}')"
    [[ "$expected" == "$actual" ]] || die \
"BASE IMAGE MODIFIED -- every existing sandbox is now unreliable.
  expected $expected
  actual   $actual
Rebuild with: vm build --force"
}

# Allocate the lowest free index; it determines the ssh port and peer IP.
_overlay_next_index() {
    local used=() d idx i
    for d in "$VMBOX_VMS_DIR"/*/; do
        [[ -d "$d" ]] || continue
        idx="$(meta_get "$(basename "$d")" index 2>/dev/null)" || continue
        [[ -n "$idx" ]] && used+=("$idx")
    done
    for (( i = 1; i < 200; i++ )); do
        local taken=0 u
        for u in ${used+"${used[@]}"}; do [[ "$u" == "$i" ]] && taken=1 && break; done
        (( taken )) || { printf '%d' "$i"; return 0; }
    done
    die "no free sandbox slots (200 in use?)"
}

overlay_new() {
    local name rtc="" arg
    name="$(validate_vm_name "${1:-}")"; shift || true

    while [[ $# -gt 0 ]]; do
        arg="$1"
        case "$arg" in
            --rtc) rtc="${2:-}"; [[ -n "$rtc" ]] || die "--rtc needs a timestamp"; shift 2 ;;
            *) die "unknown option for 'vm new': $arg" ;;
        esac
    done

    vm_exists "$name" && die "sandbox '$name' already exists (reset it with: vm reset $name)"
    overlay_verify_base

    local dir index
    dir="$(vm_dir "$name")"
    install -d -m 755 "$dir"
    index="$(_overlay_next_index)"

    meta_set "$name" index "$index"
    meta_set "$name" ssh_port "$(( VMBOX_SSH_PORT_BASE + index ))"
    meta_set "$name" created "$(date -Is)"
    # Stored, not passed once: every `vm run` is a fresh qemu process, so the
    # clock must be re-applied on each launch or boot #2 drifts to wall-clock.
    [[ -n "$rtc" ]] && meta_set "$name" rtc "$rtc"

    _overlay_create_disk "$name"
    ok "sandbox '$name' ready (ssh port $(( VMBOX_SSH_PORT_BASE + index )), peer ${VMBOX_GUEST_SUBNET}.${index})"
}

_overlay_create_disk() {
    local name="$1" overlay
    overlay="$(vm_overlay "$name")"
    rm -f "$overlay"
    qemu-img create -q -f qcow2 -F qcow2 -b "$VMBOX_BASE_IMG" "$overlay"
    # Belt and braces: assert the chain really points at the sealed base.
    qemu-img info --backing-chain "$overlay" | grep -q "$VMBOX_BASE_IMG" ||
        die "overlay backing chain does not reference the base image"
}

overlay_reset() {
    local name
    name="$(validate_vm_name "${1:-}")"
    require_vm "$name"
    overlay_verify_base

    vm_is_running "$name" && _overlay_stop "$name"

    # Wait for the qemu process to actually release the overlay. Recreating it
    # while the old process still has it open leaves the next boot reading a
    # half-detached file, which surfaces much later as "did not become
    # reachable" rather than as an error here.
    local waited=0 pid
    pid="$(cat "$(vm_pidfile "$name")" 2>/dev/null || true)"
    while [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && (( waited < 30 )); do
        sleep 1; waited=$(( waited + 1 ))
    done

    # Discard everything the guest did: the overlay holds 100% of its writes.
    _overlay_create_disk "$name"
    rm -f "$(vm_dir "$name")"/serial.*.log "$(vm_events "$name")" "$(vm_pidfile "$name")"
    ok "sandbox '$name' reset to pristine"
}

_overlay_stop() {
    local name="$1" pid waited=0
    pid="$(cat "$(vm_pidfile "$name")" 2>/dev/null)" || return 0
    log "Stopping running sandbox '$name'"
    kill "$pid" 2>/dev/null || true
    while kill -0 "$pid" 2>/dev/null && (( waited < 20 )); do
        sleep 1; waited=$(( waited + 1 ))
    done
    kill -9 "$pid" 2>/dev/null || true
}

overlay_rm() {
    local name
    name="$(validate_vm_name "${1:-}")"
    require_vm "$name"
    vm_is_running "$name" && _overlay_stop "$name"
    rm -rf "$(vm_dir "$name")"
    ok "sandbox '$name' deleted"
}
