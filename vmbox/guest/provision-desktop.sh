#!/bin/bash
# ============================================================================
# Runs INSIDE the guest during `vm build`, as root, called by provision.sh.
#
# Everything that gives the sandbox a real graphical session: autologin on
# tty1, startx into i3, a minimal i3 config, and the X-environment discovery
# that lets `vm run` reach that session. Split out of provision.sh to keep
# both files under the 250-line cap.
# ============================================================================

set -euo pipefail

GUEST_USER="${1:-arch}"

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

# --- X session discovery for non-login commands ---------------------------
# The image ships a real X/i3 session so locker and i3 tests can run. But
# `vm run` executes through `sh -c`, which reads no profile, so those
# commands land with no DISPLAY and no XAUTHORITY -- and every X tool then
# fails with "Could not determine i3 socket path" / "cannot open display".
# That looks exactly like "the sandbox has no X", which is wrong and cost a
# real installer run to diagnose. The resolver is its own file, guest/
# vmbox-x11.sh, because desktop-lightdm.sh re-installs it after switching a
# sandbox to lightdm (different auth-file location) -- one source for both.
install -m 644 "$(dirname "${BASH_SOURCE[0]}")/vmbox-x11.sh" /etc/profile.d/vmbox-x11.sh
