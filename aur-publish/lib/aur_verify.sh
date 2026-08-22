#!/bin/bash

# ============================================================================
# Gates a package must pass before it is allowed near the AUR.
#
# Sourced by publish.sh, never executed: these functions read the readonly
# config (AUR_ROOT, DRY_RUN) that the entry script declares, and
# a `readonly` re-run inside a twice-sourced lib would abort under `set -e`.
# ============================================================================

set -euo pipefail

newest_tag() {
    # Newest clean vX.Y.Z on the remote. Build tags (vX.Y.Z-build.N) and the
    # grafted upstream Flutter SDK tags in diet-guard are excluded on purpose.
    git -C "$1" ls-remote --tags origin 2>/dev/null |
        awk '{print $2}' |
        sed 's|refs/tags/||' |
        grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' |
        sed 's/^v//' |
        sort -V |
        tail -1
}

verify_installed() {
    local binary="$1" expected="$2" wrapper="$3" output

    # An instance left over from a previous run would make the wrapper print
    # "already running" and hand off, which passes trivially and turns the
    # strongest gate in this script into the weakest. Clear it first so the
    # check always exercises a real cold start.
    #
    # Resolved through /proc/<pid>/exe rather than any form of name or
    # command-line matching. Every argv-based approach selects the wrong
    # processes here:
    #   * `pkill -x` compares against the kernel's 15-character comm field, and
    #     two of these wrappers are longer (habit_stack_desktop is 19), so a
    #     name match would silently never fire.
    #   * `pkill -f`, and equally `ps -eo args` piped through a pattern, match
    #     any process whose command line merely *mentions* the path — this
    #     script, the shell running it, and the matching tool itself all
    #     qualify, so the run kills its own shell instead of the app. A
    #     $$/$PPID guard does not cover it, because the offending shell is
    #     often a more distant ancestor.
    # /proc/<pid>/exe is a kernel-maintained symlink to the binary actually
    # being executed, so it cannot collide with an incidental mention.
    # The wrapper name is unique per app, so the /opt/<pkg>/ segment is left as
    # a glob instead of threading the package name through another parameter.
    #
    # The link is read without `-f`: it is already fully resolved, and by the
    # time this runs `pacman -U` has replaced the binary, so a leftover process
    # points at an unlinked inode that the kernel reports with a " (deleted)"
    # suffix. That suffix has to be stripped or the match silently misses the
    # one process this exists to kill.
    local pid exe killed=()
    for pid in /proc/[0-9]*; do
        pid="${pid#/proc/}"
        exe="$(readlink "/proc/$pid/exe" 2>/dev/null)" || continue
        exe="${exe% (deleted)}"
        [[ "$exe" == /opt/*/bin/"$wrapper" ]] || continue
        kill -TERM "$pid" 2>/dev/null && killed+=("$pid")
    done
    if ((${#killed[@]})); then
        info "stopped a running instance so the launch check is meaningful"
        # `kill` only reports that the signal was sent. Waiting for the process
        # to actually go keeps a slow exit from failing the cold start below on
        # a port that is still bound.
        local waited=0
        while ((waited < 100)) && kill -0 "${killed[@]}" 2>/dev/null; do
            sleep 0.1
            ((waited++))
        done
    fi

    output="$(timeout 15 "/usr/bin/$binary" 2>&1 | head -3 || true)"
    if grep -qF "$expected" <<<"$output"; then
        return 0
    fi
    warn "unexpected startup output: $output"
    return 1
}

# The AUR does not review uploads, but "packages that violate the rules may be
# deleted without warning" (AUR submission guidelines). These are the rules that
# are mechanically checkable, enforced here so a violation blocks the push
# rather than surfacing later as a deletion request.
check_aur_rules() {
    local pkg="$1" problems=()

    grep -q '^# Maintainer:' PKGBUILD \
        || problems+=("missing '# Maintainer:' comment on line 1")

    grep -qE "^arch=\(.*x86_64" PKGBUILD \
        || problems+=("x86_64 not in arch=() — packages without it are not allowed")

    # `replaces` makes pacman rip out the named package on the next -Sy, which
    # is only correct for a genuine rename. `conflicts` is the right tool.
    grep -q '^replaces=' PKGBUILD \
        && problems+=("uses replaces=; AUR rules reserve it for renames — use conflicts=")

    # A package already in an official repo must never be duplicated.
    if pacman -Si "$pkg" >/dev/null 2>&1; then
        problems+=("$pkg exists in an official repo — must not be submitted")
    fi

    grep -qE '^(pkgdesc|url|license)=' PKGBUILD \
        || problems+=("missing pkgdesc/url/license")

    # A stale .SRCINFO is the single most common upload rejection.
    if ! diff -q <(makepkg --printsrcinfo) .SRCINFO >/dev/null 2>&1; then
        problems+=(".SRCINFO does not match PKGBUILD")
    fi

    if ((${#problems[@]})); then
        warn "$pkg: AUR rule violations:"
        printf '      - %s\n' "${problems[@]}"
        return 1
    fi
    info "AUR rule checks passed"
    return 0
}

