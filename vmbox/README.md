# vmbox — a disposable Arch VM sandbox

Run destructive system scripts — shutdown installers, `chattr +i` hosts guards,
pacman hooks — against a throwaway Arch guest, and **verify the outcome from the
host**. Break it as thoroughly as you like; reset takes under a second.

```bash
./install.sh          # installs deps (libisoburn), links `vm` onto PATH
vm build              # builds the golden image, once (~100s)
vm new demo           # instant: a ~200 KB overlay on the sealed base
vm run demo 'sudo systemctl poweroff'
vm reset demo         # back to pristine
```

## Why this exists

Much of `testsAndMisc/linux_configuration` cannot be tested on the real machine.
The repo's own CI says so — its Ubuntu job runs only the "side-effect-free"
tests and notes the rest *"drive pacman, /etc, systemd or adb and cannot run on
an Ubuntu runner without root and an Arch container"*. Locally they probe the
**live** system (`test_results.log` asserts `PASS: /etc/hosts is immutable`).

Three things make testing them on the host genuinely unsafe:

- **`chattr +i` immutability** — 15 files make `/etc/hosts` and friends
  immutable. A bad test is not simply revertable; `rm` fails with EPERM.
- **Auto-poweroff** — the shutdown installers write systemd units that power the
  machine off on a schedule.
- **Pacman hooks** — `boot_recovery/install.sh` installs pre/post-transaction
  hooks and touches mkinitcpio. Blast radius is "your next update".

## The hard part: a successful shutdown kills your observer

Running a shutdown script over SSH returns a broken pipe. That is
**indistinguishable** from a crash, a hang, or a network blip — ssh returns 255
for all of them. So "did it actually shut down?" is answered from the host,
using two artefacts that outlive the VM:

| Channel | What it proves |
|---|---|
| QMP event log (`events.jsonl`) | *That* the machine stopped, and who stopped it |
| Serial console log | *How far* the shutdown sequence got |

A persistent recorder attaches at launch, **before** anything runs in the guest.
This ordering matters: attach afterwards and QEMU has already exited, the stream
is closed, and there is no verdict to read.

### Five outcomes, all host-observable

Every row below was measured against a real Arch guest, not inferred:

| Guest command | QMP event | Verdict | Exit |
|---|---|---|---|
| `systemctl poweroff` | `SHUTDOWN {guest:true, guest-shutdown}` + serial reaches `reboot: Power down` | clean poweroff | 0 |
| a stop that dies mid-sequence | `SHUTDOWN {guest:true}`, serial truncated | **dirty** | 3 |
| `systemctl reboot` | `SHUTDOWN {guest:true, guest-reset}` | **rebooted**, did not power off | 4 |
| `echo c > /proc/sysrq-trigger` | `GUEST_PANICKED` | **crashed** | 5 |
| a script that wedges | no event, liveness probe fails | **hung** | 6 |

**ssh returned the identical `Connection closed by remote host` for the
poweroff, the reboot AND the panic.** That is the entire argument for reading
the verdict from the host rather than from the connection.

`guest:true` alone is not enough for "shuts down *completely*" — `poweroff -f`
and a script that kills systemd mid-sequence both produce it. The serial tail is
the discriminator, and it is asserted by grep, not read by eye.

> A `POWERDOWN` event is **not** proof of anything: it means the ACPI request was
> delivered. With no OS booted, QEMU emits `POWERDOWN` and then runs forever.

## Worked example: testing the real shutdown installer

```bash
vm share ~/src/digital-wellbeing            # read-only bind, not a symlink
vm share ~/src/utils/guard-lib              # the config guard it installs
vm new st --rtc 2026-08-22T20:55:00     # inside the 21:00-05:00 window
vm repo st ~/src/digital-wellbeing --worktree
vm repo st ~/src/utils/guard-lib --worktree
vm run st 'sudo bash ~/guard-lib/install.sh'
vm run st 'sudo MIDNIGHT_SHUTDOWN_CONFIRM=y bash ~/digital-wellbeing/setup_midnight_shutdown.sh enable'
vm run st 'sudo systemctl poweroff'     # -> VERDICT: clean poweroff
vm reset st                             # back to pristine
```

The full night-lockdown flow (lightdm topology, a hanging `openrgb` shim, the
per-minute timer, mask/stop, black screen, morning unlock) is scripted in
`digital-wellbeing/tests/vmbox_night_lockdown.sh` and is the reference for
how `vm lightdm` and `vm shim` fit together.

Verified: the config lands at `/etc/shutdown-schedule.conf` under guard-lib's
immutable protection, and `shutdown-timer-monitor.service`,
`day-specific-shutdown.timer` and `shutdown-timer-monitor-watchdog.timer` all
come up enabled -- while the host's own copy of that file kept its original
timestamp and `/etc/hosts` kept its `+i` flag.

Two things that installer taught us, both worth knowing before you run it:

- **It refuses to run unattended.** It ends on a confirmation prompt, and
  `vm run` closes stdin on purpose (installers that prompt would otherwise
  hang forever). Piping `echo y |` no longer works either -- with no terminal
  it declines by design. Set `MIDNIGHT_SHUTDOWN_CONFIRM=y` to proceed.
- **It is subcommand-driven** (`enable` / `status`). Bare invocation prints
  usage and exits 1 without changing anything.

## Design notes

- **Reset is a backing-file trick.** The golden image is built once and sealed
  (`chmod 444` + a sha256 sidecar verified on every launch). Each sandbox is a
  thin qcow2 overlay, so `vm reset` is `rm` + recreate. Booting the base itself
  would silently invalidate every overlay, so the launcher refuses to.
- **No root anywhere.** User-mode networking with a per-VM forwarded SSH port;
  VM-to-VM traffic rides a socket multicast segment. No bridge, no libvirt, no
  daemon.
- **The guest clock is pinned** (`--rtc`) and re-applied on *every* launch. The
  shutdown installers gate on a 21:00–05:00 window, so an unpinned clock makes
  their tests pass or fail depending on the time of day. NTP is masked in the
  image, or it would quietly undo the pin.
- **The guest gets its own clone** of the repos from a read-only mount. Real
  credentials are never shared; the guest carries sentinel values instead.

## Commands

| Command | Effect |
|---|---|
| `vm build [--force]` | Build/rebuild the golden image |
| `vm new <name> [--rtc <ts>]` | Create a sandbox |
| `vm run <name> <cmd...>` | Run a command, print the verdict |
| `vm ssh <name>` | Interactive shell (starts the VM if needed) |
| `vm screenshot <name> [out.png]` | Capture the screen (locker/X11 tests) — verified: real 1280x800 PNG of the guest's i3 session, no viewer installed |
| `vm lightdm <name>` | Switch the sandbox to the host's login topology: lightdm autologin → i3, tty1 a plain getty. Reboots the guest and proves `lightdm.service` is active with an Xorg it owns |
| `vm shim <name> <tool> [exit[:N]\|hang\|sleep:S]` | Put a fake `<tool>` ahead of the real one on PATH (`/usr/local/sbin`). Every call is logged with an epoch to `/var/log/vmbox-shim/<tool>.log`, so the host can assert what ran and in what order. `hang` reproduces a tool that never returns |
| `vm reset <name>` | Wipe back to pristine |
| `vm rm <name>` / `vm list` | Delete / list sandboxes |

## Hardware the guest does not have: shim it

The guest has no RGB controllers, no NVIDIA card and no sound card, and the
golden image logs in with agetty+startx rather than a display manager. None
of that is a reason to test on the host. `vm lightdm` gives a sandbox the
host's login units (the night-lockdown scripts mask/stop `lightdm.service`
and `getty@.service`, which do not exist under startx), and `vm shim` stands
in for `openrgb`, `nvidia-smi`, `amixer` with a chosen behaviour and a call
log. The 2026-09-12 curfew failure -- openrgb 1.0-2 never returning, before
the teardown -- is `vm shim nl openrgb hang`, and the fix is proven by the
lockdown completing anyway.

Both mutate a live overlay only. The base image is never rebuilt for this:
`vm build --force` re-seals a new checksum while every existing sandbox still
backs onto the old file's *name*, which is silent qcow2 corruption, not a
loud refusal.

## Out of scope

A VM still cannot cover adb/phone tests (~36 files), real GPU monitors, and
the Nextcloud/SearXNG suites (whose fixtures assume a Debian layout); those
stay on the host or stay untested.

## Tests

`bats tests/test_vmbox.bats` — 39 host-side unit tests for name validation,
meta handling, serial rotation and the full verdict table. They do not boot a
VM; booting is covered by the destructive end-to-end demo above.

## Speed

Measured on this host, all with the cloud image already downloaded:

| | before | after |
|---|---|---|
| `vm run` (cold sandbox) | 41s | 14s |
| `vm run` (warm sandbox) | 30s | 3s |

Neither number was the guest being slow. `_run_settle` waited up to 30s for a
poweroff marker on EVERY run, including the majority that leave the guest
running, and the ssh readiness poll used a 5s connect timeout against a
forwarded port QEMU accepts before the guest is listening on it.

A cold `vm run` also waits for the guest's X session, because sshd now answers
before tty1's autologin has started Xorg; `VMBOX_X_WAIT=<seconds>` overrides it.

The build reads packages from the host's own `/var/cache/pacman/pkg`, mounted
read-only, rather than fetching 396 MiB over the internet. The guest keeps its
own writable cache, so a package the host lacks is downloaded as usual. See
`DOCS-session-results.md` for the build before/after.
