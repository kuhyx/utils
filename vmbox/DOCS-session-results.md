# vmbox Job 1 results

## Item 1: the 8 Arch-only CI tests — 8/8 PASS
Ran in sandbox t1 (rtc pinned 2026-08-22T20:55). All eight tests the
`arch-tests` CI job names as impossible on an Ubuntu runner passed:
test_hosts_file_monitor, test_hosts_guard_pacman_integration,
test_i3blocks_efficiency, test_makepkg_capped, test_makepkg_wrapper,
test_pacman_wrapper_security, test_security_hardening, test_shutdown_timer_monitor.
vmbox bugs found: none.
NOTE: test_security_hardening reported Skipped: 17 on the bare guest -> item 2.

## Item 2: test_security_hardening.sh on a configured guest — DONE
Progression of the same test as the guest got configured:
  bare guest             Passed 0  Skipped 17
  + install_core_system  Passed 10 Skipped 14
  + guard-lib + shutdown Passed 14 Skipped 10
  + hosts-guard migrate  Passed 18 Skipped  6   Failed 0
The 6 remaining skips are legitimate: 5 are screen_locker checks (that code
moved to its own repo, gatelock migration) and 1 is the canonical hosts copy.

vmbox bug found+fixed: `vm run` gave guest commands no DISPLAY/XAUTHORITY, so
the i3 installer failed as if the sandbox had no X. Fixed in cf5982c; the
installer now exits 0. Also found: sourcing a missing file with `.` in POSIX
sh aborts the shell even with `|| true` (special-builtin rule).

### testsAndMisc findings (REPORTED, not fixed — per Q8)
1. install_core_system.sh references two paths that no longer exist:
   python_pkg/screen_locker/install_systemd.sh and
   python_pkg/steam_backlog_enforcer/install.sh. Both moved out during the
   gatelock migration. 2 of 7 modules can never install on a fresh machine.
2. The hosts/nsswitch/resolved file-guards are installed ONLY by the one-shot
   script single_use/fixes/migrate_hosts_guard_to_guard_lib.sh, never by
   hosts/install.sh — although install.sh's own comment claims guard-lib's
   "hosts" instance watches /etc/hosts. A fresh machine following the
   documented install path gets /etc/hosts chattr +i but NO watcher, NO
   canonical copy and NO bind mount. Verified both ways in the sandbox.
3. setup_midnight_shutdown.sh requires guardctl on PATH but install_core_system.sh
   never installs guard-lib first, so on a fresh machine the core "Midnight
   shutdown timer" module always fails.

## Item 5: hosts guard immutability — PASS (complete)
lsattr /etc/hosts in the guest: ----ia---------------- (189366 entries).
The immutable flag really lands.

`vm reset` clearing it: VERIFIED 2026-08-22 (was left pending). Set
`chattr +i /etc/hosts` in a sandbox -> `----i-----------------`; after
`vm reset` the same file reads `----------------------` AND accepts a write
(`echo test >> /etc/hosts` succeeds). This is the strongest form of the reset
guarantee: immutability is precisely what makes these scripts hard to undo on
a real machine, and the overlay discards it wholesale.

## Item 4: boot_recovery/install.sh — PASS (highest-value item)
Installer exits 0; installs boot-repair + both pacman hooks.
Hook firing verified BOTH ways, which is the part that matters:
  - `pacman -S sl` (trivial pkg): hooks correctly did NOT fire. Their trigger
    is Target = usr/lib/modules/*/vmlinuz, i.e. kernel transactions only.
  - `pacman -S linux` (kernel):  05-boot-mounted-guard.hook FIRED PreTransaction,
    detected /boot unmounted, and ABORTED the transaction (AbortOnFail).
    "error: failed to commit transaction" / "no packages were upgraded".
    Kernel left untouched at 7.1.9.arch1-2. This is the exact scenario that
    would leave a real machine unbootable, exercised safely.
Real `boot-repair` (not --dry-run) then repaired 2 of 6 problems:
set ParallelDownloads=1, and deleted 2 "orphaned kernel files".

### FINDING (reported, not fixed): boot-repair is UEFI-only in a way it does not check
On this BIOS/GRUB guest with no ESP, boot-repair classified the REAL
/boot/vmlinuz-linux and /boot/initramfs-linux.img as "orphaned kernel file(s)
in the unmounted /boot (shadowing the ESP)" and deleted them, leaving the
guest unbootable (confirmed: it never boots again; `vm reset` restores it).
On kuhy's actual UEFI machine that heuristic is right. On any BIOS/GRUB
system it destroys the only bootable kernel. Worth a guard.

## vmbox bugs #2/#3 found + fixed (commit 8bb4d3a)
The unbootable guest above made `vm run` hang instead of failing:
 - vm_wait_ssh counted only its sleeps, not the up-to-5s ConnectTimeout each
   failed probe spends inside ssh -> a "150s" wait ran past 400s.
   Now a wall-clock deadline: same guest reported unreachable in 156s.
 - _run_recover_rc fell through to an unbounded serial read (180+300s) AFTER
   the verdict was already printed. Now bounded 60s/30s.

## Item 3: setup_night_lockdown.sh — PASS except the hardware RGB (as predicted)
Exit 0. Verified in the guest:
  /etc/night-lockdown.conf written (user=arch uid=1000, GPU_UNBIND_ENABLE=0)
  /usr/local/bin/night-lockdown-enter.sh + -unlock.sh installed
  night-lockdown-unlock.timer enabled, NEXT = Sun 2026-08-23 05:00:00 UTC
    (correct against the PINNED clock -- proves --rtc reaches the timer layer)
  /etc/modules-load.d/night-lockdown-i2c.conf written; /dev/i2c-0 present
NOT APPLICABLE IN A VM: rgb-off.service fails 127 -- `/usr/bin/openrgb` is not
installed (no RGB hardware to drive). Exactly the carve-out the handoff called.

## Job 1 summary: 5/5 items done. 3 vmbox bugs found, all fixed+pushed.
## Job 3: build speed

### The stated baseline was wrong, and that matters for reading these numbers
The handoff says "~10 min". Measured here: **103.76s**. The 10-minute figure
included the one-time 531 MB cloud-image download, which is cached now. So
"faster than ~10 min" would have been true before I changed anything; the
honest comparison is against 103.76s.

### Build: 103.76s -> 99.99s, i.e. ~4%. Small, and here is why
(99.99s is the confirming rebuild from committed source; smoke test passed.)
Per-phase instrumentation (added this session) shows where it actually goes:

  PHASE first-boot   47s   the build guest's cloud-init first boot
  PHASE provision    28-37s installing 195 packages
  (rest)             ~20s  image copy, resize, seal, smoke test

Idea 1 (host pacman cache, Q7) WORKS and is committed: the 396.04 MiB the
build used to download is now read from /var/cache/pacman/pkg. `pacman` no
longer prints a "Total Download Size" line at all. But it only bought ~5s of
the provision phase, because on a 986 Mbps line 396 MiB was never the
bottleneck -- unpacking 1273 MiB was. Worth keeping (it makes the build work
offline, and stops re-downloading what is already on disk) but it is not the
speed win the handoff expected.

Idea 3 (cut the cloud-init wait) did NOT pan out, and the measurement says why:
`cloud-init analyze blame` totals **2.27s** of actual work, and `search-NoCloud`
is 0.23s of that. The 47s is not datasource probing. I tried starting sshd
early via cloud-init `bootcmd` (`runcmd` is too late -- it is in
cloud_final_modules); no change. The build guest genuinely takes ~47s to first
boot, and I did not find the mechanism. NOT DONE -- see "still open".

### The real win was elsewhere: `vm run` got 3-4x faster
Chasing the build number turned up two flat taxes on EVERY sandbox command:

  vm run, cold sandbox   41s -> 14s   (includes waiting for the X session)
  vm run, warm sandbox   30s ->  3s

- `_run_settle` waited up to 30s for the kernel's "reboot: Power down" marker
  unconditionally, including on the majority of runs that leave the guest
  running, where it can never appear.
- The ssh readiness poll used a 5s ConnectTimeout. QEMU's user-mode networking
  ACCEPTS the forwarded connection before the guest listens on :22, so each
  probe blocked for the full timeout instead of failing fast: a guest
  reachable at ~10s was reported up at ~45s.

All five shutdown verdicts re-tested on BOTH transports (ssh and serial), plus
tests/destructive_demo.sh 7/7.

A first attempt at this gated the skip on the transport's exit code, which
BROKE the serial path: ssh returns 255 for a poweroff but serial_exec returns
0 while the machine is already going down, so a clean serial-driven poweroff
was reported as "still running" -- vmbox's whole purpose, silently wrong.
Grepping the serial log at that instant does not work either (the markers
appear a second or two later). The shipped version waits a short grace period
for any sign of a stop before committing to the long wait.

### Host cache safety (Q7's gate)
Fingerprinted before and after FOUR full builds: 45427 files,
121783272583 bytes, identical mtime. **Host cache provably unmodified.**
Enforced at both layers: `readonly=on` on the QEMU virtfs AND `ro` at mount.

## Still open (honest list)
- The 47s build first-boot is unexplained. cloud-init's own work is 2.27s, the
  network is up at 9.8s, the config stage is done at 11.6s, and then nothing
  is logged until 44s. Worth one focused session with `systemd-analyze
  critical-chain` on a build-mode guest.
- boot-repair's BIOS/GRUB kernel deletion is REPORTED, not fixed (per Q8).
