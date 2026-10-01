#!/bin/bash
# ============================================================================
# vmbox: optional UEFI firmware (OVMF) for a sandbox.
#
# The default stays SeaBIOS: every existing sandbox and test was measured on
# it, and nothing here changes a sandbox that did not opt in. UEFI is chosen
# per sandbox (`vm new <name> --uefi`, stored in meta) or per launch
# (`VMBOX_FIRMWARE=uefi|bios`, which `vm run <name> --uefi` sets).
#
# The cloud image boots both ways unmodified: it carries an ESP at /efi with
# the removable-media loader EFI/BOOT/BOOTX64.EFI, which is the ONLY path a
# fresh varstore tries -- so no boot entry has to be created first.
# ============================================================================

# Sourced by both launch.sh and overlay.sh, and launch_vm sources overlay.sh
# at call time -- so a second source must be a no-op, not a readonly error.
[[ -n "${VMBOX_FIRMWARE_SOURCED:-}" ]] && return 0
readonly VMBOX_FIRMWARE_SOURCED=1

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# edk2-ovmf's own descriptor for the 4 MB non-secure-boot build on q35. Read
# rather than hard-coded so a package layout change moves us with it.
readonly VMBOX_OVMF_DESCRIPTOR="${VMBOX_OVMF_DESCRIPTOR:-/usr/share/qemu/firmware/60-edk2-ovmf-x86_64-4m.json}"

# Per-sandbox NVRAM. It must persist across launches: systemd stores the
# hibernation resume location (HibernateLocation) here, so a fresh copy per
# boot would silently turn every UEFI resume into a cold boot.
vm_efivars() { printf '%s/%s/efivars.fd' "$VMBOX_VMS_DIR" "$1"; }

# $1 = executable | nvram-template. Env overrides win over the descriptor.
_firmware_file() {
    local kind="$1" path=""
    case "$kind" in
        executable)     path="${VMBOX_OVMF_CODE:-}" ;;
        nvram-template) path="${VMBOX_OVMF_VARS:-}" ;;
    esac
    if [[ -z "$path" ]]; then
        [[ -r "$VMBOX_OVMF_DESCRIPTOR" ]] ||
            die "no OVMF descriptor at $VMBOX_OVMF_DESCRIPTOR -- install edk2-ovmf ($VMBOX_ROOT/install.sh)"
        # Checked here, not in require_host_deps: only UEFI needs jq, and a
        # BIOS-only host must keep working without it.
        command -v jq >/dev/null || die "UEFI mode needs jq -- run: $VMBOX_ROOT/install.sh"
        path="$(jq -er --arg k "$kind" '.mapping[$k].filename // empty' "$VMBOX_OVMF_DESCRIPTOR")" ||
            die "OVMF descriptor $VMBOX_OVMF_DESCRIPTOR has no mapping.$kind.filename"
    fi
    [[ -r "$path" ]] || die "OVMF $kind not readable: $path"
    printf '%s' "$path"
}

# Effective firmware for the next launch: per-launch env, then meta, then bios.
firmware_of() {
    local name="$1" fw
    fw="${VMBOX_FIRMWARE:-$(meta_get "$name" firmware 2>/dev/null || true)}"
    fw="${fw:-bios}"
    case "$fw" in
        bios|uefi) printf '%s' "$fw" ;;
        *) die "unknown firmware '$fw' (expected bios or uefi)" ;;
    esac
}

# Fresh varstore from the template. Called by `vm new --uefi`, by `vm reset`
# (a "pristine" sandbox must not keep the last run's boot entries or
# HibernateLocation), and lazily the first time a BIOS sandbox boots as UEFI.
firmware_init_vars() {
    local name="$1" vars template
    vars="$(vm_efivars "$name")"
    # Explicit exits: callers use `|| firmware_init_vars`, and set -e is off
    # inside anything called from an || list.
    template="$(_firmware_file nvram-template)" || exit 1
    install -m 644 "$template" "$vars" || die "could not create $vars"
}

# Append the sandbox's firmware args to the array named by $2; none for bios.
# A nameref, not printed output read back through a process substitution: a
# `die` inside one is swallowed, and a missing OVMF would then quietly boot
# the sandbox as BIOS -- the opposite of what was asked for.
firmware_qemu_args() {
    local name="$1" fw code vars
    local -n _fw_out="$2"
    fw="$(firmware_of "$name")" || exit 1
    [[ "$fw" == uefi ]] || return 0
    code="$(_firmware_file executable)" || exit 1
    vars="$(vm_efivars "$name")"
    [[ -f "$vars" ]] || firmware_init_vars "$name"
    # Unit 0 read-only: the firmware code is a shared system file. Unit 1 is
    # this sandbox's own NVRAM copy, writable.
    _fw_out+=(
        -drive "if=pflash,format=raw,unit=0,readonly=on,file=$code"
        -drive "if=pflash,format=raw,unit=1,file=$vars"
    )
}
