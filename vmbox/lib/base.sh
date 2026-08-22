#!/bin/bash
# ============================================================================
# vmbox: golden base image build.
#
# Downloads the signed Arch cloud image, provisions it once, then SEALS it:
# chmod 444 + a sha256 sidecar. Every sandbox is a thin qcow2 overlay on this
# file, so booting the base even once would silently corrupt every overlay
# derived from it -- hence the seal and the launch-time verification.
# ============================================================================

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
# shellcheck source=seed.sh
source "$(dirname "${BASH_SOURCE[0]}")/seed.sh"
# shellcheck source=smoke.sh
source "$(dirname "${BASH_SOURCE[0]}")/smoke.sh"

readonly CLOUD_URL="https://geo.mirror.pkgbuild.com/images/latest"
readonly CLOUD_IMG="Arch-Linux-x86_64-cloudimg.qcow2"
readonly BASE_DISK_SIZE="${BASE_DISK_SIZE:-20G}"
readonly BUILD_SSH_PORT="${BUILD_SSH_PORT:-2222}"

base_fetch() {
    # Separate statements: within a single `local a=.. b="$a.."`, the later
    # reference is unbound under `set -u` because the assignment is not done yet.
    local dest="$VMBOX_BASE_DIR/cloudimg.qcow2"
    local tmp="$dest.tmp"
    local sums="$dest.SHA256"
    [[ -f "$dest" ]] && { log "Cloud image present, skipping download"; return 0; }

    install -d -m 755 "$VMBOX_BASE_DIR"
    log "Downloading Arch cloud image (~531 MB)"
    curl -fL --progress-bar -o "$tmp" "$CLOUD_URL/$CLOUD_IMG"
    curl -fsSL -o "$sums" "$CLOUD_URL/$CLOUD_IMG.SHA256"

    local expected actual
    expected="$(awk '{print $1}' "$sums")"
    actual="$(sha256sum "$tmp" | awk '{print $1}')"
    [[ "$expected" == "$actual" ]] ||
        die "checksum mismatch -- refusing to use image (expected $expected, got $actual)"
    mv "$tmp" "$dest"
    ok "cloud image verified"
}

# Boot the working copy with the seed ISO and an ssh forward, provision over
# ssh (real exit codes, unlike driving a shell over the serial console), then
# shut down cleanly.
base_provision() {
    local disk="$1" work seed serial qpid
    work="$(mktemp -d)"
    seed="$work/seed.iso"
    serial="$VMBOX_BASE_DIR/build.log"
    rm -f "$serial"

    seed_ensure_key
    seed_build_iso "$seed" "$work"

    log "Booting image for provisioning"
    qemu-system-x86_64 \
        -machine q35,accel=kvm -cpu host -smp 4 -m 4096 \
        -drive file="$disk",if=virtio,format=qcow2 \
        -drive file="$seed",if=virtio,format=raw,readonly=on \
        -netdev "user,id=net0,hostfwd=tcp:127.0.0.1:${BUILD_SSH_PORT}-:22" \
        -device virtio-net-pci,netdev=net0 \
        -display none \
        -chardev file,id=ser0,path="$serial",append=on -serial chardev:ser0 \
        -no-reboot >/dev/null 2>&1 &
    qpid=$!

    # Always reap the build VM, including on failure or Ctrl-C. The pid and
    # workdir are baked into the trap body: a RETURN trap fires after the
    # function's locals are gone, so referencing $qpid there is unbound.
    # shellcheck disable=SC2064  # expanding NOW is intended: see comment above
    trap "kill $qpid 2>/dev/null || true; rm -rf '$work'" RETURN

    _base_wait_ssh "$qpid" || die "guest never became reachable -- see $serial"

    log "Provisioning guest (installs Xorg/i3 + dev tools; several minutes)"
    _base_scp "$VMBOX_GUEST_DIR/provision.sh" "/tmp/provision.sh"
    _base_ssh "chmod +x /tmp/provision.sh && sudo /tmp/provision.sh '$VMBOX_GUEST_USER'" ||
        die "provisioning failed -- see $serial"

    # Disable cloud-init so per-VM boots skip datasource probing entirely
    # (it adds startup delay and would re-run on every overlay).
    #
    # Do NOT run `cloud-init clean` here: on this image cloud-init is what
    # brings sshd up, and cleaning strips that alongside its own state,
    # producing a sealed image whose guests boot fine but are unreachable.
    # provision.sh enables sshd.service independently, which is what makes
    # disabling cloud-init safe at all.
    _base_ssh "sudo touch /etc/cloud/cloud-init.disabled" || true

    # Assert the sealed image will actually be reachable. A base that boots but
    # refuses ssh is the single most expensive failure here: it looks like a
    # network bug and costs a full rebuild to find.
    _base_ssh "test -e /etc/systemd/system/multi-user.target.wants/sshd.service" ||
        die "sshd.service is not enabled in the image -- guests would be unreachable"
    ok "verified: sshd.service will start on boot"

    log "Shutting the build VM down cleanly"
    _base_ssh "sudo systemctl poweroff" >/dev/null 2>&1 || true

    local waited=0
    while kill -0 "$qpid" 2>/dev/null && (( waited < 120 )); do
        sleep 2; waited=$(( waited + 2 ))
    done
    kill -0 "$qpid" 2>/dev/null && { warn "build VM did not stop; forcing"; kill "$qpid"; }
    ok "provisioning complete"
}

_base_ssh_opts() {
    printf '%s' "-i $VMBOX_SSH_KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
-o LogLevel=ERROR -o ConnectTimeout=5 -p $BUILD_SSH_PORT"
}

_base_ssh() {
    # shellcheck disable=SC2046  # word splitting of ssh opts is intended
    ssh $(_base_ssh_opts) "${VMBOX_GUEST_USER}@127.0.0.1" "$@"
}

_base_scp() {
    scp -i "$VMBOX_SSH_KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR -P "$BUILD_SSH_PORT" "$1" "${VMBOX_GUEST_USER}@127.0.0.1:$2"
}

# ssh is its own port prober, so no nc/socat needed (neither is installed).
_base_wait_ssh() {
    local qpid="$1" waited=0
    log "Waiting for guest ssh (first boot runs cloud-init)"
    while (( waited < 300 )); do
        kill -0 "$qpid" 2>/dev/null || return 1
        if _base_ssh -o BatchMode=yes true 2>/dev/null; then
            ok "guest reachable after ${waited}s"
            return 0
        fi
        sleep 5; waited=$(( waited + 5 ))
    done
    return 1
}

# Make the base read-only and record its hash. The hash is the guard that
# actually catches corruption; chmod alone can be bypassed.
base_seal() {
    local disk="$1"
    log "Sealing base image"
    mv "$disk" "$VMBOX_BASE_IMG"
    chmod 444 "$VMBOX_BASE_IMG"
    sha256sum "$VMBOX_BASE_IMG" | awk '{print $1}' > "$VMBOX_BASE_SHA"
    ok "base sealed: $VMBOX_BASE_IMG ($(du -h "$VMBOX_BASE_IMG" | cut -f1))"
}

base_build() {
    require_host_deps
    if [[ -f "$VMBOX_BASE_IMG" && "${1:-}" != "--force" ]]; then
        die "base image already exists -- rebuild with: vm build --force"
    fi
    base_fetch

    local disk="$VMBOX_BASE_DIR/building.qcow2"
    rm -f "$disk"
    cp --reflink=auto "$VMBOX_BASE_DIR/cloudimg.qcow2" "$disk"
    qemu-img resize -q "$disk" "$BASE_DISK_SIZE"

    base_provision "$disk"
    base_seal "$disk"
    base_smoke_test
    echo
    ok "Done. Create a sandbox with: vm new demo"
}
