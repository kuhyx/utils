#!/bin/bash
# ============================================================================
# vmbox: shared paths, logging and validation.
# Sourced by every other lib/ file and by bin/vm. Defines no side effects.
# ============================================================================

# Guard against double-sourcing: each lib sources common.sh unconditionally.
# shellcheck disable=SC2034  # every path/const below is consumed by the
# sibling lib/*.sh files that source this one, which shellcheck cannot see.
[[ -n "${VMBOX_COMMON_SOURCED:-}" ]] && return 0
readonly VMBOX_COMMON_SOURCED=1

# Repo root is the parent of lib/, resolved through symlinks so the CLI works
# when bin/vm is symlinked onto PATH by install.sh.
VMBOX_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly VMBOX_LIB_DIR
# Go up one real directory rather than stripping a "/lib" suffix: the suffix
# form silently yields the wrong root when sourced via a relative path.
VMBOX_ROOT="$(cd "$VMBOX_LIB_DIR/.." && pwd -P)"
readonly VMBOX_ROOT
readonly VMBOX_GUEST_DIR="$VMBOX_ROOT/guest"

# State lives OUTSIDE the repo: these are multi-GB disk images and live
# sockets, and the repo has a pre-commit hook that blocks binaries.
readonly VMBOX_HOME="${VMBOX_HOME:-$HOME/.local/share/vmbox}"
readonly VMBOX_BASE_DIR="$VMBOX_HOME/base"
readonly VMBOX_VMS_DIR="$VMBOX_HOME/vms"
readonly VMBOX_BASE_IMG="$VMBOX_BASE_DIR/base.qcow2"
readonly VMBOX_BASE_SHA="$VMBOX_BASE_DIR/base.qcow2.sha256"
readonly VMBOX_SSH_KEY="$VMBOX_BASE_DIR/id_ed25519"

# Base SSH port. Each VM gets VMBOX_SSH_PORT_BASE + its index.
readonly VMBOX_SSH_PORT_BASE="${VMBOX_SSH_PORT_BASE:-2300}"
# Shared multicast segment so sandboxes can reach each other (no root, no bridge).
readonly VMBOX_MCAST="${VMBOX_MCAST:-230.0.0.1:12345}"
# Guest static subnet on the second NIC (the mcast segment has no DHCP).
readonly VMBOX_GUEST_SUBNET="${VMBOX_GUEST_SUBNET:-10.77.0}"

readonly VMBOX_GUEST_USER="${VMBOX_GUEST_USER:-arch}"

# Colours only when stdout is a terminal, so logs stay clean when piped.
if [[ -t 1 ]]; then
    readonly C_RED=$'\033[0;31m' C_GRN=$'\033[0;32m' C_YLW=$'\033[0;33m'
    readonly C_BLU=$'\033[0;34m' C_OFF=$'\033[0m'
else
    readonly C_RED='' C_GRN='' C_YLW='' C_BLU='' C_OFF=''
fi

log()  { printf '%s==>%s %s\n' "$C_BLU" "$C_OFF" "$*"; }
ok()   { printf '%s ok %s %s\n' "$C_GRN" "$C_OFF" "$*"; }
warn() { printf '%s warn%s %s\n' "$C_YLW" "$C_OFF" "$*" >&2; }
die()  { printf '%serror%s %s\n' "$C_RED" "$C_OFF" "$*" >&2; exit 1; }

# VM names become directory names and qemu -name values; keep them boring.
validate_vm_name() {
    local name="${1:-}"
    [[ -n "$name" ]] || die "vm name is required"
    [[ "$name" =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]{0,31}$ ]] ||
        die "invalid vm name '$name' (allowed: alphanumeric, _ and -, max 32 chars)"
    printf '%s' "$name"
}

vm_dir()      { printf '%s/%s' "$VMBOX_VMS_DIR" "$1"; }
vm_overlay()  { printf '%s/%s/overlay.qcow2' "$VMBOX_VMS_DIR" "$1"; }
vm_meta()     { printf '%s/%s/meta' "$VMBOX_VMS_DIR" "$1"; }
vm_qmp_sock() { printf '%s/%s/qmp.sock' "$VMBOX_VMS_DIR" "$1"; }
# Separate control channel: the recorder occupies the main QMP socket, and a
# QMP socket accepts a single client at a time.
vm_qmp_ctl()  { printf '%s/%s/qmp.sock.ctl' "$VMBOX_VMS_DIR" "$1"; }
# Bidirectional serial console. Unlike ssh this survives the poweroff it is
# reporting on, and it works when sshd does not -- so it is the transport of
# record for shutdown tests, not a fallback.
vm_console()  { printf '%s/%s/console.sock' "$VMBOX_VMS_DIR" "$1"; }
vm_events()   { printf '%s/%s/events.jsonl' "$VMBOX_VMS_DIR" "$1"; }
vm_pidfile()  { printf '%s/%s/vm.pid' "$VMBOX_VMS_DIR" "$1"; }

# Serial logs are per-boot: a relaunch must never overwrite the log a verdict
# is about to be read from. See vm_next_serial().
vm_serial()   { printf '%s/%s/serial.%s.log' "$VMBOX_VMS_DIR" "$1" "$2"; }

vm_exists() { [[ -d "$(vm_dir "$1")" ]]; }

require_vm() {
    vm_exists "$1" || die "no such vm: '$1' (create it with: vm new $1)"
}

# meta is a flat key=value file; values must not contain newlines.
meta_get() {
    local name="$1" key="$2" line
    line="$(grep -m1 "^${key}=" "$(vm_meta "$name")" 2>/dev/null)" || return 1
    printf '%s' "${line#*=}"
}

meta_set() {
    local name="$1" key="$2" value="$3" meta
    meta="$(vm_meta "$name")"
    [[ "$value" == *$'\n'* ]] && die "meta value for '$key' must be single-line"
    touch "$meta"
    # Rewrite in place: delete any existing key, then append the new value.
    grep -v "^${key}=" "$meta" > "$meta.tmp" 2>/dev/null || true
    printf '%s=%s\n' "$key" "$value" >> "$meta.tmp"
    mv "$meta.tmp" "$meta"
}

# Highest existing serial.N.log + 1, so each boot writes its own file.
vm_next_serial() {
    local name="$1" n=0 f
    # -e guards the unmatched-glob case; without it an empty dir yields either
    # a literal "serial.*.log" (bash) or a hard error (zsh).
    for f in "$(vm_dir "$name")"/serial.*.log; do
        [[ -e "$f" ]] || continue
        local base="${f##*/serial.}"
        base="${base%.log}"
        [[ "$base" =~ ^[0-9]+$ ]] && (( base >= n )) && n=$(( base + 1 ))
    done
    printf '%d' "$n"
}

# A VM is running if its pidfile names a live qemu process. Stale pidfiles are
# normal: a guest that powers itself off leaves one behind.
vm_is_running() {
    local pid
    pid="$(cat "$(vm_pidfile "$1")" 2>/dev/null)" || return 1
    [[ -n "$pid" ]] || return 1
    [[ -r "/proc/$pid/cmdline" ]] || return 1
    grep -qa vmbox-"$1" "/proc/$pid/cmdline" 2>/dev/null
}

require_host_deps() {
    local missing=()
    command -v qemu-system-x86_64 >/dev/null || missing+=(qemu-base)
    command -v qemu-img          >/dev/null || missing+=(qemu-img)
    command -v xorrisofs         >/dev/null || missing+=(libisoburn)
    command -v python3           >/dev/null || missing+=(python)
    (( ${#missing[@]} == 0 )) ||
        die "missing host dependencies: ${missing[*]} -- run: $VMBOX_ROOT/install.sh"
}
