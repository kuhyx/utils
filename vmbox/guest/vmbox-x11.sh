#!/bin/sh
# Installed to /etc/profile.d/vmbox-x11.sh by provision-desktop.sh (golden
# image) and re-installed by desktop-lightdm.sh (per-sandbox lightdm switch).
# Sourced by `vm run`; POSIX sh, because /etc/profile.d may be read by dash.
#
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
    # Prefer the auth file the running Xorg was actually started with. Test
    # READABILITY, not existence: under lightdm that is /run/lightdm/root/:0,
    # root-only, and the user's cookie is ~/.Xauthority instead. The startx
    # serverauth glob is the last resort for the golden image's tty1 session.
    _vmbox_xauth="$(tr '\0' '\n' < /proc/"$(pgrep -x Xorg | head -1)"/cmdline 2>/dev/null \
        | grep -A1 -x -- -auth | tail -1)"
    if [ ! -r "${_vmbox_xauth:-}" ]; then
        _vmbox_xauth="$HOME/.Xauthority"
    fi
    if [ ! -r "${_vmbox_xauth:-}" ]; then
        for _vmbox_cand in /tmp/serverauth.*; do
            [ -r "$_vmbox_cand" ] && _vmbox_xauth="$_vmbox_cand"
        done
        unset _vmbox_cand
    fi
    if [ -r "${_vmbox_xauth:-}" ]; then
        XAUTHORITY="$_vmbox_xauth"
        export XAUTHORITY
    fi
    unset _vmbox_xauth
fi
# i3 tools look here when I3SOCK is unset; setting it explicitly avoids a
# second round of X round-trips in tests that shell out repeatedly.
if [ -n "${DISPLAY:-}" ] && [ -z "${I3SOCK:-}" ] && command -v i3 >/dev/null 2>&1; then
    I3SOCK="$(i3 --get-socketpath 2>/dev/null || true)"
    if [ -n "$I3SOCK" ]; then export I3SOCK; else unset I3SOCK; fi
fi
