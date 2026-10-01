# RTC wake emulation (`vm wake`) and UEFI mode

Tests the "PC wakes itself" flow (wake-alarm's `rtcwake -m no -t <epoch>` +
hibernate or poweroff) in a sandbox:

```bash
vm new rw --uefi                       # or without --uefi (SeaBIOS, default)
VMBOX_MEM=2048 vm hibernate-setup rw   # swap + resume= (overlay only)
vm wake rw --accel 10 -- 'sudo rtcwake -m no -s 120 && sudo systemctl hibernate'
bash tests/rtcwake_e2e.sh [--uefi]     # the end-to-end proof, see below
```

Run anything that boots a guest under
`~/.claude/scripts/capped.sh` (`CAP_MEM=4G CAP_CPU_PCT=20`) with
`VMBOX_MEM=2048`: a 4 GiB guest does not fit a 4 GiB cap.

## Why the firmware half is emulated

Measured on this host (qemu 11.1.1, edk2-ovmf 202608, q35, 2026-10-01). The
guest armed an alarm, went down, and we waited well past it:

| Guest goes to | Firmware | CMOS after the alarm time | QEMU |
|---|---|---|---|
| S3 (`rtcwake -m mem`) | SeaBIOS | — | `SUSPEND`, then **`WAKEUP` 20 s later** — native |
| S5 (`systemctl poweroff`) | SeaBIOS | REG_C = 0xB0 (alarm flag set) | stays `shutdown` |
| S4 (`rtcwake -m disk`) | SeaBIOS | REG_C = 0xB0 | stays `shutdown` |
| S5 | OVMF | REG_C = 0xB0 | stays `shutdown` |
| S4 (`systemctl hibernate`) | OVMF | REG_C = 0xB0 | stays `shutdown` |

In every S4/S5 row the guest had also set `RTC_EN` in ACPI `PM1_EN`
(0x0520 / 0x0720) and AIE in REG_B — everything a real chipset needs. QEMU
only acts on a wakeup request while the machine is *suspended* (S3); a
powered-off machine has no wake path at all. So `vm wake` plays the board:
it reads the alarm, waits, and presses the power button.

## VM artefacts around a resume

All four were found by the e2e test, each broke a resume the guest itself
had done correctly, and none exists on real hardware. A hibernate resume in
QEMU is always a relaunch of the process, so any device state that lived
only in the old process is gone when the guest's drivers pick up again:

- **kvmclock.** A KVM guest's persistent clock is kvmclock, i.e. the HOST's
  wall clock. A cold boot still follows the RTC (rtc_cmos `hctosys`), but a
  resume does not: powered on with its RTC at the alarm instant, a guest
  resumed **102 s before its own alarm**. Real hardware reads the CMOS on
  resume. `vm hibernate-setup` therefore adds `no-kvmclock`, and `vm wake`
  fails with exit 14 (`clock-not-from-rtc`) when the guest clock is behind
  the alarm it was powered on at, instead of passing silently.
- **TCO watchdog.** Every resumed guest was reset ~20 s in
  (`WATCHDOG action=reset`; the native S3 wake hit the same ~34 s in).
  Measured on the ICH9 TCO block at 0x660: `TCO_TMR` (0x672) reads 0x0032
  after a cold boot — the driver's 30 s heartbeat at 0.6 s/tick — and
  0x0004, QEMU's 2.4 s reset default, right after a resume, while the
  resumed driver still reports `timeout=30`. A fresh QEMU process lost the
  value, the restored driver does not reprogram it, and its 15 s pings
  cannot beat a 2.4 s timer. `vm wake` powers on with
  `-action watchdog=none` (`VMBOX_WATCHDOG_ACTION`): expiries are still
  logged in `events.jsonl` (one per ping, every 15 s), but ignored. The
  guest's own watchdog setup is untouched.
- **9p host share.** Observed: after a resume every access to
  `/mnt/hostrepo` blocked, and the next poweroff sat 4.5 min in "A stop job
  is running for /mnt/hostrepo"; unmounting before and remounting after
  fails with "no channels available for device hostrepo", and unbinding the
  device after the resume hangs. Inferred, not verified: 9pnet_virtio does
  not re-create its virtqueue on restore. What works (measured):
  `hibernate-setup`'s system-sleep hook unmounts and unbinds the device
  before hibernating, then rebinds and remounts it after.
- **Display (NOT fixed).** virtio-gpu fences never complete after a resume:
  Xorg — the resumed one and a freshly started one alike — sits in
  `dma_fence_default_wait`. Anything that needs X after a resume cannot be
  tested here. `guest/vmbox-x11.sh` now bounds its one X call
  (`i3 --get-socketpath`), which had hung every later `vm run`;
  `hibernate-setup` installs that copy, since older base images bake in the
  unbounded one.

## What `vm wake` does

1. Boots the sandbox if needed, then `set-action shutdown=pause` over QMP — the
   runtime form of `-no-shutdown`. Launch defaults are untouched; only this
   run's machine pauses instead of exiting when the guest goes down.
2. Runs the guest command over ssh and waits (bounded,
   `VMBOX_WAKE_DOWN_TIMEOUT`, 240 s) for QMP `SHUTDOWN`. `SUSPEND_DISK` right
   before it means hibernate (ACPI S4); anything else (reboot, panic) is exit 13.
3. Reads the **stopped** guest's CMOS through HMP port I/O
   (`lib/rtc_alarm.py`): alarm sec/min/hour (0x01/0x03/0x05), REG_B (AIE,
   BCD/binary, 12/24 h), `PM1_EN` at 0x602, and the RTC itself via
   `qom-get /machine rtc-time`. Register C is never read — reading clears it.
   QEMU's FADT has no day alarm ("alarms up to one day"), so the wake instant
   is the next time the RTC matches h:m:s — the hardware's own comparison.
4. AIE off → `NO WAKE ARMED`, the machine is left off, exit 9.
5. Waits `ceil(lead / accel)` real seconds (`--accel`, default 1; refuses with
   exit 12 beyond `--max-wait`, default 900 s).
6. Quits QEMU and relaunches it with `-rtc base=<alarm instant>` (one-shot
   `VMBOX_RTC_ONCE`; the sandbox's `--rtc` pin is never rewritten), on the
   **same** RAM, SMP and firmware the guest went down on — read from the
   running QEMU's `/proc/<pid>/cmdline`, because a resume on different RAM
   discards the image. For S5 that is a cold boot; for S4 the kernel resumes
   from swap. Exit 11 if ssh does not answer within 180 s.
7. Prints `RTCWAKE key=value` lines (below) and `WAKE: … after its alarm`;
   exit 14 if the guest's clock came back behind the alarm (see below).

Relaunching instead of resuming the paused process is faithful, not a
shortcut: in S4/S5 only the disk and the CMOS survive on real hardware, and
both are carried over (the overlay is the disk; the RTC base is the clock).

| Key | Meaning |
|---|---|
| `down` | `poweroff` or `hibernate` |
| `rtc_at_down` | guest RTC when the harness read the CMOS |
| `cmos_regs`, `aie`, `rtc_en` | raw registers and the two enable bits |
| `armed_epoch`, `armed_utc` | decoded alarm (RTC read as UTC, like `rtcwake`) |
| `lead_guest_s` | alarm − RTC at read time |
| `accel`, `waited_real_s` | acceleration and the real wait |
| `poweron_rtc` | RTC the machine was powered on with |
| `back_after_real_s` | relaunch → ssh answering, wall clock |
| `up_after_alarm_guest_s` | guest `date +%s` at first ssh − alarm |
| `result` | `woke` (0), `not-armed` (9), `never-down` (10), `not-back` (11), `too-far` (12), `wrong-stop:*` (13), `clock-not-from-rtc` (14) |

## UEFI mode

`vm new <name> --uefi` stores `firmware=uefi` in meta and copies
`OVMF_VARS.4m.fd` to the sandbox's `efivars.fd`; `vm run <name> --uefi …`
overrides one launch (a BIOS sandbox gets its varstore on first UEFI boot).
Paths come from edk2-ovmf's descriptor
`/usr/share/qemu/firmware/60-edk2-ovmf-x86_64-4m.json`
(`VMBOX_OVMF_CODE`/`VMBOX_OVMF_VARS` override). A missing OVMF is an error,
never a silent BIOS boot.

- The cloud image boots both ways unmodified: its ESP (`/efi`) carries
  `EFI/BOOT/BOOTX64.EFI`, the only loader a fresh varstore tries.
- The varstore persists across launches (systemd keeps `HibernateLocation`
  there) and is re-copied by `vm reset`.
- `vm list` shows a `FW` column. The base image is unchanged.

## `vm hibernate-setup`

The base image has a 512 MiB btrfs swapfile and a systemd initramfs, but no
`resume=`: a hibernated BIOS guest cold-boots and logs `PM: Image not found`.
`guest/hibernate-setup.sh` grows `/swap/swapfile` to RAM + 512 MiB
(`btrfs filesystem mkswapfile`), adds `resume=UUID=… resume_offset=…
no-kvmclock` to `GRUB_CMDLINE_LINUX_DEFAULT`, regenerates `grub.cfg` (shared
by the BIOS and EFI GRUB), reboots, and proves it: those args in
`/proc/cmdline` and logind `CanHibernate` = `yes`. Overlay only — never
`vm build --force`.

`vm run <name> 'sudo systemctl hibernate'` now reports `VERDICT: hibernated`
(exit 8) instead of a DIRTY shutdown, and skips the exit-code recovery boot,
which would have consumed the image.

## What this proves, and what only the host can

Proven in the VM (by `tests/rtcwake_e2e.sh`):

- the wake instant is armed correctly: the alarm decoded from the CMOS
  equals the guest's own `/sys/class/rtc/rtc0/wakealarm`;
- it **survives the guest going down**, for poweroff and for hibernate — the
  value is read *after* the stop, with AIE and `RTC_EN` still set;
- after a power-on at that instant the guest comes back: a boot-time unit
  runs after the alarm (poweroff), or the same boot resumes with a
  pre-hibernate process alive and the post-resume hook run (hibernate);
- an alarm disabled before going down leaves the machine off (exit 9).

Not proven — host only:

- **that real firmware wakes at all.** That is the whole emulated part. The
  host's S4 wake was verified separately (wake-alarm
  `DOCS-wake-enforcement.md`); S5 stays unverified until tested on the host.
- firmware quirks: a BIOS setting that disables RTC wake, an RTC kept in
  local time, a board that ignores `RTC_EN` from S5, a day-of-month alarm
  (QEMU has none, so alarms > 24 h ahead cannot be modelled);
- boot/resume *duration* on real hardware, and the real disk/ESP layout;
- anything graphical after a resume (the guest display is dead, above), and
  how real GPU/audio/USB drivers come back from S4;
- the guest's wall clock after resume follows the RTC only because of
  `no-kvmclock`; on the host it is the firmware's CMOS, as it should be.

Report a green run as "passed in vmbox, not verified on the host".
