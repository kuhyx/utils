# Next session: make vmbox the default place scripts get tested

Paste everything below into a fresh Claude session.

---

`~/utils/vmbox` is a working disposable-Arch-VM sandbox (built and verified
2026-08-22, pushed to `github.com/kuhyx/utils`). Read `~/utils/vmbox/README.md`
first — it documents the design and the traps.

Two jobs this session, in order.

## Job 1: harden it by using it for real

vmbox has only ever been driven by one session, against a handful of scripts.
`testsAndMisc/linux_configuration` is ~1090 files, ~170 of which need root.
**Expect it to break.** That is the point of this job: find the breakages by
running real work through it, and fix them.

Work through this list, fixing vmbox whenever it gets in the way:

1. The 8 Arch-only tests the repo's CI already names in
   `.github/workflows/shell-tests.yml` (`arch-tests` job) — `test_hosts_*`,
   `test_makepkg_*`, `test_pacman_wrapper_security.sh`,
   `test_security_hardening.sh`, `test_shutdown_timer_monitor.sh`. These are
   the ones its comments say "cannot run on an Ubuntu runner". Run them in a
   sandbox and report which pass.
2. `test_security_hardening.sh` specifically: on a bare guest it reports its
   host checks as *skipped*. Install the real system first
   (`install_core_system.sh`), then re-run it, so those checks become real.
3. `setup_night_lockdown.sh` — writes `/etc/systemd/system` units and an
   i2c module config. The i2c RGB part is hardware and will not work; confirm
   everything else does.
4. `boot_recovery/install.sh` — pacman hooks + mkinitcpio. Highest blast
   radius of anything in the repo, and the best argument for the sandbox.
5. The hosts guard (`periodic_background/hosts/install.sh`) — rewrites
   `/etc/hosts` and makes it immutable with `chattr +i`. Verify the immutable
   flag really lands in the guest, then that `vm reset` clears it.

For each: `vm share` what it needs, clone into the guest, run it, report what
happened. When vmbox itself is the thing that broke, fix vmbox and commit.

### Known-good invocation shape

```bash
vm share ~/testsAndMisc            # bind mount, NOT a symlink (9p won't follow one)
vm share ~/utils                   # guard-lib lives here; several scripts need guardctl
vm new t1 --rtc 2026-08-22T20:55:00   # pin the clock: shutdown scripts gate on 21:00-05:00
vm run t1 'git clone --no-hardlinks -q /mnt/hostrepo/testsAndMisc ~/tam'
vm run t1 'echo y | sudo bash ~/tam/path/to/script.sh enable'   # many prompt; stdin is closed
vm reset t1                        # ~2s back to pristine
```

### Traps already paid for — do not rediscover these

- **A guest that boots but refuses ssh is almost never a network problem.**
  Run `systemctl list-jobs` on the guest via `vm ssh` or the serial console. A
  unit that is enabled, has satisfied dependencies, and neither starts nor
  fails is QUEUED behind something. That cost most of a session.
- **Never grep a `bash -x` trace for the failure** — you find where your
  pattern matched, not where execution stopped. Read the tail.
- **`pkill -f <pattern>`** kills the Bash-tool shell when the pattern appears
  in the command running it (exit 144). Use `pgrep -f | xargs -r kill`.
- Full list: `~/.claude/projects/-home-kuhy/memory/reference-vmbox-guest-image-traps.md`
  and `reference-qemu-shutdown-verification.md`.

### Rebuilding the image

`vm build --force` takes ~10 min. It ends with a smoke test that boots a real
sandbox and refuses to ship an unreachable image. **Do not debug the image by
rebuilding per hypothesis** — boot an overlay off the current base, fix it live
over the serial console (root autologin is on ttyS0 and ttyS1), confirm the
fix, and only then bake it into `guest/provision.sh` and rebuild once.

## Job 2: make it the default, once Job 1 says it is trustworthy

kuhy's ask: *"claude should ALWAYS defer to using this sandbox when testing
stuff, ESPECIALLY when testing scripts."*

**Do Job 2 only after Job 1.** A rule that routes work into a tool that
breaks is worse than no rule. If Job 1 leaves vmbox flaky, say so and stop.

The rule belongs in `~/.claude/CLAUDE.md`. Points to settle with kuhy before
writing it — these are real forks, not rhetorical:

- **What triggers it.** "Any script" is too broad: it would send a one-line
  `python_pkg` unit test through a VM boot. A sharper line is anything that
  needs root, writes outside `$HOME`, touches systemd/pacman/`/etc`, or could
  power the machine off.
- **What it replaces.** Today's `CLAUDE.md` development workflow says "run the
  actual script to verify it does what it is supposed to do". Does the sandbox
  become the *first* run, or an extra step before the host run? Note the
  standing `feedback-verify-real-deployment-path` memory: testing somewhere
  that is not the real deploy target has burned kuhy before, so a sandbox pass
  must NOT be presented as proof the host is fine.
- **The escape hatch.** Anything hardware-bound (adb/phone, GPU, i2c, the
  Huion tablet) cannot run in a VM. The rule needs a stated exception, or it
  will be violated on the first phone task and quietly stop being followed.
- **Where it lives.** `CLAUDE.md` is always-on context, so keep it to a few
  lines and link out. Per `token-spend.instructions.md`, a long rule there is
  a permanent per-turn tax.

Draft it, get kuhy's sign-off on those four points, then write it.

## Definition of done

- The 5 items in Job 1 have been run in a sandbox, with results reported per
  item (pass / fail / not-applicable-in-a-VM, with reasons).
- Every vmbox bug found is fixed, committed, and pushed.
- `bats ~/utils/vmbox/tests/test_vmbox.bats`, shellcheck and ruff all clean.
- Either the CLAUDE.md rule is written and agreed, or there is a clear
  statement of what still makes vmbox untrustworthy.

## State as of handoff

Verified working: the shutdown verdict (5 outcomes, all measured against real
guests), destructive demo 7/7, reset ~2s, VM-to-VM ping (0% loss), screenshots,
pinned clock, repo share + clone, base-corruption guard, build smoke gate.

Unverified / not attempted: everything in Job 1 above; anything hardware-bound;
concurrent sandboxes beyond two.
