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
# The image ships a real X/i3 session on tty1 so locker and i3 tests can run.
# But `vm run` executes through `sh -c`, which reads no profile, so those
# commands land with no DISPLAY and no XAUTHORITY -- and every X tool then
# fails with "Could not determine i3 socket path" / "cannot open display".
# That looks exactly like "the sandbox has no X", which is wrong and cost a
# real installer run to diagnose.
#
# XAUTHORITY is the awkward half: startx generates /tmp/serverauth.XXXXXXXX
# with a random suffix on every boot, so it cannot be hardcoded. Resolve it
# from the running Xorg process instead, falling back to a glob.
cat > /etc/profile.d/vmbox-x11.sh <<'XENV'
# Point non-login shells at the guest's X session, if one is running.
# Sourced by vmbox's `vm run`; harmless when no X session exists.
if [ -z "${DISPLAY:-}" ]; then
    # Wait briefly for the X session rather than reporting "no X".
    #
    # vmbox now returns control as soon as sshd answers (~11s), which is
    # EARLIER than getty@tty1 autologin has run .bash_profile and started
    # Xorg. Without this wait the first `vm run` after a boot silently gets
    # no DISPLAY and every X tool fails as if the sandbox had no X server --
    # the exact failure this file exists to prevent, reintroduced by making
    # the rest of the tool faster. Bounded, and skipped entirely once Xorg
    # is up, so a guest with no graphical session costs at most this wait.
    # Default 0: a plain `vm run` must not pay for a graphical session it is
    # not using. Set VMBOX_X_WAIT=<seconds> for X11/i3/locker work.
    _vmbox_x_wait="${VMBOX_X_WAIT:-0}"
    while [ "$_vmbox_x_wait" -gt 0 ]; do
        pgrep -x Xorg >/dev/null 2>&1 && break
        sleep 1
        _vmbox_x_wait=$((_vmbox_x_wait - 1))
    done
    unset _vmbox_x_wait
    if pgrep -x Xorg >/dev/null 2>&1; then
        DISPLAY=":0"
        export DISPLAY
    fi
fi
if [ -n "${DISPLAY:-}" ] && [ -z "${XAUTHORITY:-}" ]; then
    # Prefer the auth file the running Xorg was actually started with.
    _vmbox_xauth="$(tr '\0' '\n' < /proc/"$(pgrep -x Xorg | head -1)"/cmdline 2>/dev/null \
        | grep -A1 -x -- -auth | tail -1)"
    if [ ! -f "${_vmbox_xauth:-}" ]; then
        _vmbox_xauth="$(ls -1t /tmp/serverauth.* 2>/dev/null | head -1)"
    fi
    if [ -f "${_vmbox_xauth:-}" ]; then
        XAUTHORITY="$_vmbox_xauth"
        export XAUTHORITY
    fi
    unset _vmbox_xauth
fi
# i3 tools look here when I3SOCK is unset; setting it explicitly avoids a
# second round of X round-trips in tests that shell out repeatedly.
if [ -n "${DISPLAY:-}" ] && [ -z "${I3SOCK:-}" ] && command -v i3 >/dev/null 2>&1; then
    I3SOCK="$(i3 --get-socketpath 2>/dev/null || true)"
    [ -n "$I3SOCK" ] && export I3SOCK || unset I3SOCK
fi
XENV
chmod 644 /etc/profile.d/vmbox-x11.sh
