#!/bin/bash
# ============================================================================
# Runs INSIDE a sandbox as root, via `vm lightdm <name>`.
#
# Switch the guest's graphical session from the golden image's agetty+startx
# autologin to a display manager, mirroring kuhy's real machine: lightdm with
# autologin straight into i3, tty1 a plain login. Scripts that mask/stop
# lightdm.service and getty@.service (night-lockdown) have nothing to act on
# under startx; here they get the same units the host has.
#
# Applied to a live overlay, never to the base image: `vm build --force`
# would silently corrupt every existing sandbox (their backing file changes
# underneath them), so the topology change is a per-sandbox step instead.
# Takes effect after a reboot, which the host side performs.
# ============================================================================

set -euo pipefail

GUEST_USER="${1:-arch}"
readonly MARKER="/etc/vmbox-desktop"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "$MARKER" && "$(cat "$MARKER")" == "lightdm" ]]; then
    echo "desktop-lightdm: already converted"
    exit 0
fi

# -Syu, not -S: the overlay's package database is the golden image's, so a
# plain -S asks mirrors for versions they have already rotated out (404 on
# adwaita-fonts, seen 2026-09-13), and a partial upgrade is unsupported anyway.
# The host's pacman cache is mounted read-only, so most of this is local.
pacman -Syu --noconfirm --needed lightdm lightdm-gtk-greeter >/dev/null
echo "desktop-lightdm: lightdm installed"

# Same shape as the host's /etc/lightdm/lightdm.conf: autologin with no
# greeter delay, into the i3 session that i3-wm ships in /usr/share/xsessions.
# Arch's lightdm only honours autologin for members of the `autologin` group.
groupadd -r -f autologin
gpasswd -a "$GUEST_USER" autologin >/dev/null
install -d -m 755 /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/50-vmbox-autologin.conf <<CONF
[Seat:*]
greeter-session=lightdm-gtk-greeter
user-session=i3
autologin-user=${GUEST_USER}
autologin-user-timeout=0
autologin-session=i3
CONF

# tty1 becomes a plain getty, as on the host: drop the autologin drop-in and
# the startx-on-tty1 hook, or two X servers would fight over the seat.
rm -f /etc/systemd/system/getty@tty1.service.d/autologin.conf
rmdir /etc/systemd/system/getty@tty1.service.d 2>/dev/null || true
cat > "/home/$GUEST_USER/.bash_profile" <<'PROFILE'
[[ -f ~/.bashrc ]] && . ~/.bashrc
PROFILE
chown "$GUEST_USER:$GUEST_USER" "/home/$GUEST_USER/.bash_profile"

# lightdm starts Xorg with -auth /run/lightdm/root/:0, readable by root only;
# the user's session cookie is ~/.Xauthority. Re-install the DISPLAY resolver
# `vm run` sources from its single source, which already prefers whichever
# auth file is readable -- older golden images carry a version that does not.
install -m 644 "$HERE/vmbox-x11.sh" /etc/profile.d/vmbox-x11.sh

systemctl daemon-reload
systemctl enable lightdm.service >/dev/null 2>&1
systemctl set-default graphical.target >/dev/null 2>&1
echo lightdm > "$MARKER"
echo "desktop-lightdm: lightdm.service enabled, autologin ${GUEST_USER} -> i3 (reboot to apply)"
