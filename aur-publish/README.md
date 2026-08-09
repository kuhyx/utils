# aur-publish

Hands-off publishing of kuhy's Flutter apps to the AUR.

```bash
~/utils/aur-publish/publish.sh              # wait for registration, then publish
~/utils/aur-publish/publish.sh --dry-run    # everything except the push
~/utils/aur-publish/publish.sh --skip-wait  # account already works
~/utils/aur-publish/publish.sh --only habit-stack
```

## What it does

1. Polls `/register` until AUR signup reopens, opens it in a browser and
   prints the SSH key to paste. **Signup is the only manual step** — it
   requires email confirmation.
2. Waits for `ssh aur@aur.archlinux.org` to authenticate.
3. Then, unattended, per package: resolve the newest `vX.Y.Z` tag → set
   `pkgver` → `updpkgsums` → `makepkg -C` → `namcap` → AUR rule check →
   `pacman -U` → launch check → `.SRCINFO` → commit → push.

Every package is built, installed and **launched** before it is pushed, so a
broken package cannot reach the AUR. A package failing any gate is skipped and
reported; the others still publish. Safe to re-run.

## anubis_gate.py

The AUR sits behind [Anubis](https://anubis.techaro.lol/), which answers HTML
requests with a proof-of-work challenge page carrying **HTTP 200**. A plain
`curl` therefore reports 200 for a page that is actually unreachable — which is
exactly how "is registration back?" gets answered wrong. This module solves the
challenge and reports the status of the *real* page behind it.

```bash
python3 anubis_gate.py /register     # prints the true status code
```

## AUR rules enforced before pushing

The AUR does not review uploads, but per the submission guidelines "packages
that violate the rules may be deleted without warning". `check_aur_rules()`
blocks a push on the mechanically checkable ones: `# Maintainer:` line,
`x86_64` in `arch`, no `replaces=` (reserved for renames — use `conflicts`),
not already in an official repo, `pkgdesc`/`url`/`license` present, and
`.SRCINFO` matching the PKGBUILD.
