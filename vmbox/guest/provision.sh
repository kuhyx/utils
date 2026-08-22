#!/bin/bash
# ============================================================================
# Runs INSIDE the guest during `vm build`, as root, exactly once.
# Installs the test surface (Xorg/i3, dev tools), wires serial+autologin,
# then leaves the image ready to be sealed.
# ============================================================================

set -euo pipefail

GUEST_USER="${1:-arch}"

echo "=== vmbox provision: starting ==="

# --- host package cache (read-only) ---------------------------------------
# The host shares its own /var/cache/pacman/pkg on the `pkgcache` 9p tag. Every
# package this image installs is usually already in it, so reading them from
# there instead of the internet is the single biggest lever on build time.
#
# Mounted `ro` -- belt and braces with the `readonly=on` on the QEMU side --
# because this is the REAL host's package cache, not a copy. It is added as an
# EXTRA CacheDir, listed BEFORE the guest's own: pacman reads from every
# CacheDir but only ever writes to the first WRITABLE one, so a package the
# host cache lacks still downloads into the guest's own cache instead of
# failing the build.
if [[ -n "$(grep -s pkgcache /proc/self/mountinfo)" ]] || mountpoint -q /mnt/pkgcache; then
    :  # already mounted
else
    install -d -m 755 /mnt/pkgcache
    if mount -t 9p -o trans=virtio,version=9p2000.L,ro pkgcache /mnt/pkgcache 2>/dev/null; then
        echo "provision: host pacman cache mounted read-only ($(ls /mnt/pkgcache | wc -l) files)"
        # CacheDir is multi-valued; the guest's own writable dir stays first.
        sed -i 's|^#*CacheDir.*|CacheDir = /var/cache/pacman/pkg/\nCacheDir = /mnt/pkgcache/|' \
            /etc/pacman.conf
        grep -q '^CacheDir' /etc/pacman.conf || printf 'CacheDir = /var/cache/pacman/pkg/\nCacheDir = /mnt/pkgcache/\n' >> /etc/pacman.conf
    else
        echo "provision: no host pacman cache share; packages will be downloaded"
    fi
fi

# The cloud image ships an empty package DB; -Syu also picks up any security
# fixes since the image was cut.
pacman -Syu --noconfirm --needed \
    base-devel git openssh sudo python python-pip \
    xorg-server xorg-xinit xorg-xrandr xorg-xset i3-wm xterm dmenu \
    strace jq bats shellcheck kcov rsync inetutils \
    iproute2 nftables which less vim

# --- serial console -------------------------------------------------------
# The verdict logic reads the serial log to tell a clean poweroff from one
# that died mid-sequence, so the guest must actually WRITE its console there.
# We keep the VGA device for screenshots, so we cannot rely on -nographic's
# implicit redirect: request ttyS0 explicitly on the kernel cmdline.
if [[ -f /etc/default/grub ]]; then
    sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT="\(.*\)"/GRUB_CMDLINE_LINUX_DEFAULT="\1 console=tty0 console=ttyS0,115200"/' \
        /etc/default/grub
    grub-mkconfig -o /boot/grub/grub.cfg 2>/dev/null || true
fi
systemctl enable serial-getty@ttyS0.service
# ttyS1 carries the interactive console vmbox drives programmatically.
systemctl enable serial-getty@ttyS1.service

# --- ssh ------------------------------------------------------------------
# `systemctl enable sshd` alone is NOT enough on this image: systemd's
# ssh-generator provides a socket-activated AF_UNIX unit, so the enable can
# no-op and leave nothing listening on TCP:22. The guest then boots perfectly
# and every ssh gets "Connection reset by peer". Force the real service on and
# verify the symlink exists, failing the build loudly if it does not.
# Do NOT `systemctl disable sshd.socket` here. On Arch sshd.socket and
# sshd.service are alternatives, and disabling the socket after enabling the
# service also drops the service's multi-user.target.wants symlink -- the
# build then reports "enabled" while the sealed image has no sshd at boot.
# Evidence: the build log shows "Created symlink" for every other unit but
# never for sshd.service, and the guest boot shows only the AF_UNIX socket.
systemctl enable sshd.service
if [[ ! -e /etc/systemd/system/multi-user.target.wants/sshd.service ]]; then
    echo "provision: FAILED to enable sshd.service -- guest would be unreachable" >&2
    exit 1
fi
# Host keys: sshd is "enabled" but FAILS TO START without them, which looks
# identical to a network fault from the host side. Generate now and assert.
ssh-keygen -A
ls /etc/ssh/ssh_host_*_key >/dev/null 2>&1 || {
    echo "provision: FAILED to generate sshd host keys" >&2
    exit 1
}
# Belt and braces. On this image sshd.service is enabled and its dependencies
# are satisfied, yet it produces no start line at boot -- neither started nor
# failed. Rather than keep guessing at the mechanism, force it explicitly once
# multi-user is reached. Harmless if sshd already started.
cat > /etc/systemd/system/vmbox-sshd-kick.service <<'KICK'
[Unit]
Description=vmbox: ensure sshd is actually running
After=multi-user.target network.target
[Service]
Type=oneshot
ExecStart=/usr/bin/systemctl start --no-block sshd.service
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
KICK
systemctl enable vmbox-sshd-kick.service

echo "provision: sshd.service enabled with $(ls /etc/ssh/ssh_host_*_key | wc -l) host keys"

# --- systemd --user session ----------------------------------------------
# Several target scripts use `systemctl --user`, which needs a real session
# bus. Lingering gives the user one without an interactive login.
loginctl enable-linger "$GUEST_USER" 2>/dev/null || true

# --- serial console autologin -------------------------------------------
# Debuggability: when ssh is broken, the serial console is the ONLY way in.
# Without autologin here an unreachable guest can only be diagnosed by
# inferring from absent log lines, which is exactly how a single sshd fault
# turned into several blind image rebuilds.
for tty in ttyS0 ttyS1; do
    install -d -m 755 "/etc/systemd/system/serial-getty@${tty}.service.d"
    cat > "/etc/systemd/system/serial-getty@${tty}.service.d/autologin.conf" <<SUNIT
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --keep-baud 115200,57600,38400,9600 %I \$TERM
SUNIT
done

# --- host repo share ------------------------------------------------------
# Mounted read-only; the guest clones out of it rather than working in it.
install -d -m 755 /mnt/hostrepo
if ! grep -q hostrepo /etc/fstab 2>/dev/null; then
    echo 'hostrepo /mnt/hostrepo 9p trans=virtio,version=9p2000.L,ro,nofail 0 0' >> /etc/fstab
fi

# --- graphical session + X discovery --------------------------------------
# Autologin on tty1, startx into i3, and the DISPLAY/XAUTHORITY resolution
# that lets `vm run` reach that session. Separate file for the 250-line cap.
bash "$(dirname "${BASH_SOURCE[0]}")/provision-desktop.sh" "$GUEST_USER"

# --- static IP on the VM-to-VM segment ------------------------------------
# The multicast segment has no DHCP (the user-mode NIC serves the other
# interface), so without a static address sandboxes cannot reach each other.
# The last octet is injected per-VM at launch via the vmbox.peer kernel arg.
cat > /usr/local/bin/vmbox-peer-ip <<'PEER'
#!/bin/bash
# Bring up the VM-to-VM segment and give this guest a static address.
#
# The address comes from the NIC's own MAC (the host allocates
# 52:54:00:be:ef:<index>), NOT from a kernel argument: deriving it here means
# the guest needs nothing passed in, so there is no way for the launcher and
# the guest to disagree about which index this VM has.
set -euo pipefail
subnet="${VMBOX_SUBNET:-10.77.0}"
for path in /sys/class/net/*/address; do
    dev="$(basename "$(dirname "$path")")"
    [[ "$dev" == lo ]] && continue
    mac="$(cat "$path")"
    # Only the peer NIC carries the be:ef prefix; the primary nic must not be
    # touched, since it carries ssh.
    [[ "$mac" == 52:54:00:be:ef:* ]] || continue
    idx=$((16#${mac##*:}))
    ip addr add "${subnet}.${idx}/24" dev "$dev" 2>/dev/null || true
    ip link set "$dev" up
    exit 0
done
PEER
chmod 755 /usr/local/bin/vmbox-peer-ip
chmod 755 /usr/local/bin/vmbox-peer-ip

cat > /etc/systemd/system/vmbox-peer-ip.service <<'PSVC'
[Unit]
Description=vmbox peer network address
After=network.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/vmbox-peer-ip
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
PSVC
systemctl enable vmbox-peer-ip.service

systemctl enable systemd-networkd systemd-resolved 2>/dev/null || true

# --- keep the pinned clock pinned -----------------------------------------
# The host passes -rtc base=<ts> so time-gated scripts (the shutdown installers
# key off a 21:00-05:00 window) are deterministic. systemd-timesyncd reaches
# the network on boot and silently overwrites that with real time, which
# re-introduces exactly the nondeterminism -rtc exists to remove.
systemctl disable systemd-timesyncd 2>/dev/null || true
systemctl mask systemd-timesyncd 2>/dev/null || true
# CRITICAL: systemd-time-wait-sync waits for a sync that can never arrive once
# timesyncd is masked. It then sits in "start running" forever and every other
# job -- sshd included -- queues behind it as "start waiting", so the system
# never reaches multi-user.target. The guest boots to a login prompt and looks
# healthy while being permanently unreachable. Mask it together with timesyncd.
systemctl disable systemd-time-wait-sync 2>/dev/null || true
systemctl mask systemd-time-wait-sync 2>/dev/null || true
# Do NOT write a /etc/systemd/network/*.network file here: an en* match
# also catches the primary NIC and outranks the cloud image's own DHCP
# config, which breaks sshd's network and makes the sandbox unreachable.
# (Learned the hard way -- it cost a full rebuild.) Masking the unit above is
# sufficient to keep the pinned clock; UseNTP only matters if timesyncd runs.
# cloud-init also writes an NTP config on some images; neutralise it.
rm -f /etc/systemd/timesyncd.conf.d/*.conf 2>/dev/null || true

echo "=== vmbox provision: done ==="
