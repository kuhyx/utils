#!/bin/bash
# ============================================================================
# vmbox: assemble the qemu command line and start a sandbox.
#
# Every observation channel the verdict logic depends on is wired here:
#   - QMP socket + a persistent event recorder (started BEFORE the guest can
#     act, so a fast poweroff cannot race it)
#   - per-boot serial log (append, never truncate)
#   - pvpanic, so a kernel panic is distinguishable from a clean stop
# ============================================================================

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

readonly VMBOX_MEM="${VMBOX_MEM:-4096}"
readonly VMBOX_SMP="${VMBOX_SMP:-4}"

# $1 = vm name. Echoes the serial-log index it started.
# First VM on the segment listens; later ones connect to it. Plain TCP on
# loopback, so this works where multicast does not.
_peer_netdev() {
    if (exec 3<>/dev/tcp/127.0.0.1/"$VMBOX_HUB_PORT") 2>/dev/null; then
        exec 3<&- 2>/dev/null || true
        printf 'connect=127.0.0.1:%s' "$VMBOX_HUB_PORT"
    else
        printf 'listen=127.0.0.1:%s' "$VMBOX_HUB_PORT"
    fi
}

launch_vm() {
    local name="$1"
    require_vm "$name"

    vm_is_running "$name" && { log "sandbox '$name' is already running"; return 0; }

    source "$VMBOX_LIB_DIR/overlay.sh"
    overlay_verify_base

    local overlay port index rtc serial_n serial qmp share
    overlay="$(vm_overlay "$name")"
    port="$(meta_get "$name" ssh_port)"
    index="$(meta_get "$name" index)"
    rtc="$(meta_get "$name" rtc 2>/dev/null || true)"
    serial_n="$(vm_next_serial "$name")"
    serial="$(vm_serial "$name" "$serial_n")"
    qmp="$(vm_qmp_sock "$name")"
    # Repos you want testable go here. Use `vm share <path>` -- it BIND-MOUNTS
    # rather than symlinks, because 9p exports a directory tree and will not
    # follow a symlink pointing outside it (the guest would see a dangling
    # link). Nothing outside this directory is ever exposed.
    share="${VMBOX_SHARE:-$VMBOX_HOME/share}"
    install -d -m 755 "$share"

    # Refuse to boot the base itself -- doing so would corrupt every overlay.
    [[ "$(realpath "$overlay")" == "$(realpath "$VMBOX_BASE_IMG")" ]] &&
        die "refusing to boot the base image directly"

    rm -f "$qmp"

    # shellcheck disable=SC2054  # commas are qemu option syntax, not separators
    local -a args=(
        -name "vmbox-$name"
        -machine q35,accel=kvm -cpu host
        -smp "$VMBOX_SMP" -m "$VMBOX_MEM"
        -drive file="$overlay",if=virtio,format=qcow2
        -netdev "user,id=net0,hostfwd=tcp:127.0.0.1:${port}-:22"
        -device virtio-net-pci,netdev=net0
        # Shared segment so sandboxes can reach each other. No root, no bridge.
        # listen= for the first VM up, connect= for the rest (see _peer_netdev).
        -netdev "socket,id=net1,$(_peer_netdev)"
        -device "virtio-net-pci,netdev=net1,mac=52:54:00:be:ef:$(printf '%02x' "$index")"
        # Repos under test, mounted PHYSICALLY read-only. Scoped to an
        # explicit share dir -- NEVER $HOME, which would hand the guest
        # ~/.ssh, ~/.claude and ~/.config/crdt-sync. The guest clones out of
        # this into its own home before touching anything.
        -virtfs "local,path=$share,mount_tag=hostrepo,security_model=mapped-xattr,readonly=on"
        -display none
        -device virtio-vga
        -chardev file,id=ser0,path="$serial",append=on
        -serial chardev:ser0
        # ttyS1: interactive console on a unix socket. Separate from ttyS0 so
        # driving a shell never interleaves with the log the verdict reads.
        -chardev "socket,id=ser1,path=$(vm_console "$name"),server=on,wait=off"
        -serial chardev:ser1
        -qmp "unix:${qmp},server=on,wait=off"
        # A QMP socket serves ONE client, and the recorder holds that one for
        # the VM's whole life. Screenshots and status queries therefore need
        # their own channel or they block until the recorder exits.
        -qmp "unix:${qmp}.ctl,server=on,wait=off"
        -device pvpanic
        # A guest *reset* becomes a SHUTDOWN(guest-reset) event, which is how a
        # script that reboots instead of powering off is caught.
        -no-reboot
        -action panic=pause
        -pidfile "$(vm_pidfile "$name")"
    )

    [[ -n "$rtc" ]] && args+=(-rtc "base=$rtc")

    _launch_qemu "$name" "$serial" "$qmp" args
    printf '%s' "$serial_n"
}

_launch_qemu() {
    local name="$1" serial="$2" qmp="$3"
    local -n argref="$4"

    qemu-system-x86_64 "${argref[@]}" >/dev/null 2>>"$serial.qemu-stderr" &
    disown

    # Wait for the QMP socket, then attach the recorder BEFORE anything runs in
    # the guest: attaching after the fact loses the SHUTDOWN event entirely
    # (qemu exits, the stream closes, and there is no verdict to read).
    local waited=0
    while [[ ! -S "$qmp" ]] && (( waited < 100 )); do
        sleep 0.1; waited=$(( waited + 1 ))
    done
    [[ -S "$qmp" ]] || die "qemu did not create a QMP socket -- see $serial.qemu-stderr"

    nohup python3 "$VMBOX_LIB_DIR/recorder.py" "$qmp" "$(vm_events "$name")" \
        >/dev/null 2>&1 &
    disown
}
