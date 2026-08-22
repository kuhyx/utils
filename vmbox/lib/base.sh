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
# The host's own package cache, offered to the build guest read-only.
readonly HOST_PKG_CACHE="${VMBOX_HOST_PKG_CACHE:-/var/cache/pacman/pkg}"

# Per-phase timing. "The build got faster" is only checkable against phase
# numbers: a single wall-clock figure hides which change did the work, and
# the download share in particular varies with what the host cache holds.
_phase_start=0
phase_begin() { printf -v _phase_start '%(%s)T' -1; log "$1"; }
phase_end() {
    local now
    printf -v now '%(%s)T' -1
    ok "$1: $(( now - _phase_start ))s"
}

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

    # Offer the host's own pacman cache to the build guest, READ-ONLY. The
    # host cache already holds every package this image installs, so this is
    # the difference between fetching them over the internet and reading them
    # off local disk.
    #
    # Read-only is enforced at BOTH layers -- `readonly=on` here and `ro` in
    # the guest's mount -- because a guest that could write here would be
    # writing into the real host system's package cache, which is the one
    # thing this design must never allow. The guest still keeps its own
    # writable /var/cache/pacman/pkg; this mount is only an extra CacheDir,
    # so a package the host cache lacks is downloaded normally rather than
    # failing the build.
    local -a cache_args=()
    if [[ -d "$HOST_PKG_CACHE" ]]; then
        cache_args=(-virtfs
            "local,path=$HOST_PKG_CACHE,mount_tag=pkgcache,security_model=none,readonly=on")
        log "Sharing the host pacman cache read-only ($(du -sh "$HOST_PKG_CACHE" 2>/dev/null | cut -f1))"
    else
        warn "no host pacman cache at $HOST_PKG_CACHE -- packages will be downloaded"
    fi

    log "Booting image for provisioning"
    qemu-system-x86_64 \
        -machine q35,accel=kvm -cpu host -smp 4 -m 4096 \
        -drive file="$disk",if=virtio,format=qcow2 \
        -drive file="$seed",if=virtio,format=raw,readonly=on \
        -netdev "user,id=net0,hostfwd=tcp:127.0.0.1:${BUILD_SSH_PORT}-:22" \
        -device virtio-net-pci,netdev=net0 \
        "${cache_args[@]}" \
        -display none \
        -chardev file,id=ser0,path="$serial",append=on -serial chardev:ser0 \
        -no-reboot >/dev/null 2>&1 &
    qpid=$!

    # Always reap the build VM, including on failure or Ctrl-C. The pid and
    # workdir are baked into the trap body: a RETURN trap fires after the
    # function's locals are gone, so referencing $qpid there is unbound.
    # shellcheck disable=SC2064  # expanding NOW is intended: see comment above
    trap "kill $qpid 2>/dev/null || true; rm -rf '$work'" RETURN

    phase_begin "Waiting for the provisioning guest to come up"
    _base_wait_ssh "$qpid" || die "guest never became reachable -- see $serial"
    phase_end "PHASE first-boot"

    phase_begin "Provisioning guest (installs Xorg/i3 + dev tools)"
    # provision.sh sources a sibling (provision-desktop.sh) by path, so BOTH
    # must land in the same directory in the guest -- copying only the entry
    # point produces a build that dies partway with "No such file or directory".
    _base_scp "$VMBOX_GUEST_DIR/provision.sh" "/tmp/provision.sh"
    _base_scp "$VMBOX_GUEST_DIR/provision-desktop.sh" "/tmp/provision-desktop.sh"
    _base_ssh "chmod +x /tmp/provision.sh /tmp/provision-desktop.sh && sudo /tmp/provision.sh '$VMBOX_GUEST_USER'" ||
        die "provisioning failed -- see $serial"
    phase_end "PHASE provision"

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
-o LogLevel=ERROR -o ConnectTimeout=${BUILD_SSH_CONNECT_TIMEOUT:-5} -p $BUILD_SSH_PORT"
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
    local qpid="$1" start now deadline
    log "Waiting for guest ssh (first boot runs cloud-init)"
    printf -v start '%(%s)T' -1
    deadline=$(( start + 300 ))
    # Poll every 1s against a wall-clock deadline, not every 5s against a
    # count of sleeps. The old loop over-reported by up to 5s of sleep plus
    # the ConnectTimeout each failed probe burns inside ssh, so a guest that
    # was reachable at ~22s was recorded as "reachable after 45s" -- and that
    # inflated figure was then treated as cloud-init being slow.
    while :; do
        kill -0 "$qpid" 2>/dev/null || return 1
        printf -v now '%(%s)T' -1
        (( now < deadline )) || return 1
        # Short connect timeout: QEMU's user-mode networking accepts the
        # forwarded connection before the guest listens on :22, so a probe
        # against a booting guest blocks for the WHOLE timeout rather than
        # failing fast. It must go through the env var -- ssh honours the
        # FIRST value given for an option, so a second -o here is ignored.
        if BUILD_SSH_CONNECT_TIMEOUT=1 _base_ssh -o BatchMode=yes true 2>/dev/null; then
            printf -v now '%(%s)T' -1
            ok "guest reachable after $(( now - start ))s"
            return 0
        fi
        sleep 1
    done
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
