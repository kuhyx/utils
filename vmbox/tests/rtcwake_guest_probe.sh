#!/bin/bash
# ============================================================================
# Runs INSIDE the guest (as root) for tests/rtcwake_e2e.sh.
#
#   rtcwake_guest_probe.sh install   install a boot-time unit and a resume hook
#   rtcwake_guest_probe.sh <event>   append "<event> <epoch> <boot_id>" to the log
#
# These stand in for the units a real wake flow depends on (wake-alarm's
# on-boot timer, a post-resume hook): the test asserts they RAN, and when,
# relative to the armed alarm -- not merely that the guest answered ssh.
# ============================================================================

set -euo pipefail

readonly LOG_DIR=/var/lib/vmbox-wake
readonly LOG="$LOG_DIR/log"
readonly SELF=/usr/local/sbin/vmbox-wake-probe

record() {
    local boot_id epoch
    read -r boot_id < /proc/sys/kernel/random/boot_id
    printf -v epoch '%(%s)T' -1
    install -d -m 755 "$LOG_DIR"
    printf '%s %s %s\n' "$1" "$epoch" "$boot_id" >> "$LOG"
}

install_probe() {
    install -m 755 "$0" "$SELF"
    cat > /etc/systemd/system/vmbox-wake-boot.service <<UNIT
[Unit]
Description=vmbox wake test: record that a boot happened, and when
[Service]
Type=oneshot
ExecStart=$SELF boot
[Install]
WantedBy=multi-user.target
UNIT
    # systemd-sleep runs every executable here with (pre|post) (hibernate|...).
    cat > /usr/lib/systemd/system-sleep/vmbox-wake-probe <<HOOK
#!/bin/sh
[ "\$1" = post ] && exec $SELF "resume-\$2"
exit 0
HOOK
    chmod 755 /usr/lib/systemd/system-sleep/vmbox-wake-probe
    systemctl daemon-reload
    systemctl enable vmbox-wake-boot.service
}

case "${1:-}" in
    install) install_probe ;;
    '')      echo "usage: $0 install | <event>" >&2; exit 2 ;;
    *)       record "$1" ;;
esac
