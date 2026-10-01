#!/bin/bash
# ============================================================================
# Runs INSIDE a sandbox, as root, via `vm hibernate-setup`. Makes
# `systemctl hibernate` both allowed and resumable, in the overlay only.
#
# The base image already has a 512 MiB btrfs swapfile and a systemd-based
# initramfs (which resumes from `resume=` on its own -- no mkinitcpio hook).
# What it lacks:
#   - swap big enough for the image (systemd refuses when swap < used RAM);
#   - resume=/resume_offset= on the kernel cmdline. Without them a BIOS guest
#     cold-boots and silently discards the image ("PM: Image not found").
#     UEFI guests can also resume via systemd's HibernateLocation variable,
#     but the cmdline works for both, so both get it.
#   - no-kvmclock. With kvmclock the kernel's persistent clock is the HOST's
#     wall clock, so a resumed guest ignores the RTC: `vm wake` powered a
#     guest on with its RTC at the alarm instant and it resumed 102 s BEFORE
#     its own alarm (measured 2026-10-01). A cold boot is unaffected (rtc_cmos
#     hctosys sets the clock), which is why only hibernate exposed it. Real
#     hardware reads the CMOS on resume; this makes the guest do the same.
#   - a sleep hook that unmounts the 9p host share before hibernating and
#     remounts it after. Its fids belong to the QEMU process that dies at S4;
#     after the relaunch every access to /mnt/hostrepo blocked, and the next
#     poweroff sat 4.5 min in "A stop job is running for /mnt/hostrepo"
#     (measured). Real machines have no 9p, so this only removes a VM artefact.
#   - the current /etc/profile.d/vmbox-x11.sh (if passed in as $2): the one
#     baked into older base images makes an unbounded X call, and X is
#     wedged after a resume, so every `vm run` after one hung.
#
# Usage: hibernate-setup.sh [swap-MiB [vmbox-x11.sh]]   (0 = RAM + 512 MiB)
# ============================================================================

set -euo pipefail

readonly SWAPFILE=/swap/swapfile
readonly GRUB_DEFAULT=/etc/default/grub
swap_mb="${1:-0}"
x11_profile="${2:-}"

mem_mb() {
    local key value _
    while read -r key value _; do
        [[ "$key" == MemTotal: ]] && { printf '%d' $(( value / 1024 )); return 0; }
    done < /proc/meminfo
    return 1
}

ensure_swap() {
    local want_mb="$1" have_mb=0
    [[ -f "$SWAPFILE" ]] && have_mb=$(( $(stat -c %s "$SWAPFILE") / 1048576 ))
    if (( have_mb < want_mb )); then
        echo "hibernate-setup: swapfile ${have_mb} MiB -> ${want_mb} MiB"
        swapoff "$SWAPFILE" 2>/dev/null || true
        rm -f "$SWAPFILE"
        install -d -m 700 "$(dirname "$SWAPFILE")"
        # mkswapfile sets NOCOW and allocates contiguously, which hibernation
        # to a btrfs swapfile requires.
        btrfs filesystem mkswapfile --size "${want_mb}m" "$SWAPFILE" >/dev/null
    fi
    swapon --show=NAME --noheadings | grep -qx "$SWAPFILE" || swapon "$SWAPFILE"
    grep -qE "^${SWAPFILE}[[:space:]]" /etc/fstab ||
        printf '%s none swap defaults 0 0\n' "$SWAPFILE" >> /etc/fstab
}

set_resume_cmdline() {
    local uuid offset
    uuid="$(findmnt -no UUID -T "$SWAPFILE")"
    offset="$(btrfs inspect-internal map-swapfile -r "$SWAPFILE")"
    [[ -n "$uuid" && "$offset" =~ ^[0-9]+$ ]] ||
        { echo "hibernate-setup: cannot locate $SWAPFILE (uuid='$uuid' offset='$offset')" >&2; exit 1; }
    # Idempotent: drop any previous resume tokens, then append the current ones.
    sed -i -E '/^GRUB_CMDLINE_LINUX_DEFAULT=/{
        s/ ?(resume(_offset)?=[^ "]*|no-kvmclock)//g
        s/"$/ resume=UUID='"$uuid"' resume_offset='"$offset"' no-kvmclock"/
    }' "$GRUB_DEFAULT"
    grep -q "resume_offset=$offset" "$GRUB_DEFAULT" ||
        { echo "hibernate-setup: failed to edit $GRUB_DEFAULT" >&2; exit 1; }
    grub-mkconfig -o /boot/grub/grub.cfg >/dev/null 2>&1
    grep -q "resume_offset=$offset" /boot/grub/grub.cfg ||
        { echo "hibernate-setup: grub.cfg lacks the resume args" >&2; exit 1; }
    echo "hibernate-setup: resume=UUID=$uuid resume_offset=$offset no-kvmclock (effective next boot)"
}

install_9p_hook() {
    # Unmount AND unbind while the old QEMU still answers, rebind after
    # resume. Remounting alone fails ("no channels available for device
    # hostrepo") and unbinding after the resume hangs -- measured; the likely
    # cause, not verified, is that 9pnet_virtio does not rebuild its
    # virtqueue on restore. /run is tmpfs, i.e. in the hibernation image, so
    # the device name survives the trip.
    cat > /usr/lib/systemd/system-sleep/vmbox-9p <<'HOOK'
#!/bin/sh
# vmbox: the 9p share cannot survive QEMU being relaunched (see hibernate-setup.sh).
drv=/sys/bus/virtio/drivers/9pnet_virtio
state=/run/vmbox-9p-dev
case "$1/$2" in
    pre/hibernate|pre/hybrid-sleep|pre/suspend-then-hibernate)
        mountpoint -q /mnt/hostrepo && ! timeout 10 umount /mnt/hostrepo && exit 0
        for d in "$drv"/virtio*; do
            [ "$(tr -d '\0' < "$d/mount_tag" 2>/dev/null)" = hostrepo ] || continue
            echo "${d##*/}" > "$drv/unbind" && echo "${d##*/}" > "$state"
        done ;;
    post/*)
        [ -s "$state" ] && cat "$state" > "$drv/bind" && rm -f "$state"
        mountpoint -q /mnt/hostrepo || timeout 10 mount /mnt/hostrepo ;;
esac
exit 0
HOOK
    chmod 755 /usr/lib/systemd/system-sleep/vmbox-9p
}

main() {
    [[ $EUID -eq 0 ]] || { echo "hibernate-setup: run as root" >&2; exit 1; }
    [[ "$swap_mb" =~ ^[0-9]+$ ]] || { echo "hibernate-setup: swap size must be MiB" >&2; exit 1; }
    (( swap_mb > 0 )) || swap_mb=$(( $(mem_mb) + 512 ))
    ensure_swap "$swap_mb"
    install_9p_hook
    [[ -z "$x11_profile" ]] || install -m 644 "$x11_profile" /etc/profile.d/vmbox-x11.sh
    set_resume_cmdline
}

main "$@"
