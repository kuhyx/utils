#!/bin/bash
# ============================================================================
# Runs INSIDE the guest during `vm build`, as root, exactly once.
# Installs the test surface (Xorg/i3, dev tools), wires serial+autologin,
# then leaves the image ready to be sealed.
# ============================================================================

set -euo pipefail

GUEST_USER="${1:-arch}"

echo "=== vmbox provision: starting ==="

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

# --- ssh ------------------------------------------------------------------
# `systemctl enable sshd` alone is NOT enough on this image: systemd's
# ssh-generator provides a socket-activated AF_UNIX unit, so the enable can
# no-op and leave nothing listening on TCP:22. The guest then boots perfectly
# and every ssh gets "Connection reset by peer". Force the real service on and
# verify the symlink exists, failing the build loudly if it does not.
systemctl enable sshd.service
systemctl disable sshd.socket 2>/dev/null || true
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
install -d -m 755 /etc/systemd/system/serial-getty@ttyS0.service.d
cat > /etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf <<SUNIT
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --keep-baud 115200,57600,38400,9600 %I \$TERM
SUNIT

# --- host repo share ------------------------------------------------------
# Mounted read-only; the guest clones out of it rather than working in it.
install -d -m 755 /mnt/hostrepo
if ! grep -q hostrepo /etc/fstab 2>/dev/null; then
    echo 'hostrepo /mnt/hostrepo 9p trans=virtio,version=9p2000.L,ro,nofail 0 0' >> /etc/fstab
fi

# --- X11 autologin + i3 ---------------------------------------------------
# Locker tests need a real X session on tty1. Autologin then startx.
install -d -m 755 /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<UNIT
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin ${GUEST_USER} --noclear %I \$TERM
UNIT

cat > "/home/$GUEST_USER/.xinitrc" <<'XINIT'
exec i3
XINIT
chown "$GUEST_USER:$GUEST_USER" "/home/$GUEST_USER/.xinitrc"

# startx on tty1 login only, so `vm ssh` sessions do not try to start X.
cat > "/home/$GUEST_USER/.bash_profile" <<'PROFILE'
[[ -f ~/.bashrc ]] && . ~/.bashrc
if [[ -z ${DISPLAY:-} && $(tty) == /dev/tty1 ]]; then
    exec startx -- -keeptty >~/.xsession.log 2>&1
fi
PROFILE
chown "$GUEST_USER:$GUEST_USER" "/home/$GUEST_USER/.bash_profile"

# i3 without a config prompts a wizard that blocks the session; ship a minimal one.
install -d -m 755 "/home/$GUEST_USER/.config/i3"
cat > "/home/$GUEST_USER/.config/i3/config" <<'I3'
set $mod Mod4
font pango:monospace 10
bindsym $mod+Return exec xterm
bindsym $mod+d exec dmenu_run
bindsym $mod+Shift+q kill
# Marker window so screenshot tests have something deterministic to match.
exec --no-startup-id xterm -T vmbox-ready -e 'echo VMBOX READY; exec bash'
I3
chown -R "$GUEST_USER:$GUEST_USER" "/home/$GUEST_USER/.config"

# --- static IP on the VM-to-VM segment ------------------------------------
# The multicast segment has no DHCP (the user-mode NIC serves the other
# interface), so without a static address sandboxes cannot reach each other.
# The last octet is injected per-VM at launch via the vmbox.peer kernel arg.
cat > /usr/local/bin/vmbox-peer-ip <<'PEER'
#!/bin/bash
# Assign the peer-network address from the vmbox.peer=<n> kernel argument.
set -euo pipefail
n=$(sed -n 's/.*vmbox\.peer=\([0-9]\+\).*/\1/p' /proc/cmdline)
[[ -n "$n" ]] || exit 0
subnet=$(sed -n 's/.*vmbox\.subnet=\([0-9.]\+\).*/\1/p' /proc/cmdline)
[[ -n "$subnet" ]] || subnet=10.77.0
# The peer NIC is the one WITHOUT a default route (user-mode NIC has it).
for i in /sys/class/net/e*; do
    dev=$(basename "$i")
    # Skip the primary NIC: it carries ssh and already has DHCP + a default
    # route. Touching it is how the sandbox becomes unreachable.
    ip route show default dev "$dev" | grep -q . && continue
    ip -4 addr show dev "$dev" | grep -q 'inet ' && continue
    ip addr add "${subnet}.${n}/24" dev "$dev" 2>/dev/null || true
    ip link set "$dev" up
    break
done
PEER
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
# Do NOT write a /etc/systemd/network/*.network file here: an en* match
# also catches the primary NIC and outranks the cloud image's own DHCP
# config, which breaks sshd's network and makes the sandbox unreachable.
# (Learned the hard way -- it cost a full rebuild.) Masking the unit above is
# sufficient to keep the pinned clock; UseNTP only matters if timesyncd runs.
# cloud-init also writes an NTP config on some images; neutralise it.
rm -f /etc/systemd/timesyncd.conf.d/*.conf 2>/dev/null || true

echo "=== vmbox provision: done ==="
