#!/bin/bash

# ============================================================================
# Publish kuhy's three Flutter apps to the AUR, hands-off.
#
# Run this once AUR registration is back. It:
#   1. Waits for https://aur.archlinux.org/register to stop returning 503,
#      then opens it in a browser and prints the SSH key to paste.
#      (Signup is the ONLY manual step: it needs an email confirmation, and
#      creating accounts is not something this script will do for you.)
#   2. Waits for `ssh aur@aur.archlinux.org` to authenticate.
#   3. From there, fully unattended, for each package:
#        newest release tag -> pkgver -> updpkgsums -> makepkg -C -> namcap
#        -> pacman -U -> launch check -> .SRCINFO -> clone AUR repo
#        -> commit -> push.
#
# Every package is BUILT, INSTALLED and LAUNCHED before it is pushed, so a
# broken package cannot reach the AUR. A package that fails any gate is
# skipped and reported; the others still publish.
#
# Idempotent and resumable: re-running skips work that is already done, and
# an already-published package is updated rather than duplicated.
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly GATE="$SCRIPT_DIR/anubis_gate.py"
readonly AUR_HOST="aur.archlinux.org"
readonly SSH_KEY="$HOME/.ssh/aur"
readonly AUR_ROOT="$HOME/aur"

# package:repo:wrapper-process:cli-name:expected-startup-string
# The wrapper process name is NOT derivable from the package name
# (diet-guard-app runs diet_guard_desktop), so it is listed explicitly.
readonly PACKAGES=(
    "todo-flutter:$HOME/todo:todo_desktop:todo:serving on http://localhost:8730"
    "habit-stack:$HOME/habit_stack:habit_stack_desktop:habit-stack:serving on http://localhost:8731"
    "diet-guard-app:$HOME/diet-guard:diet_guard_desktop:diet-guard-app:serving on http://localhost:8732"
)

POLL_SECONDS=300
SKIP_WAIT=0
DRY_RUN=0
ONLY=""
FAILED=()
PUBLISHED=()

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --skip-wait        Assume the account + SSH key already work; go straight
                     to building and publishing.
  --dry-run          Do everything except the final 'git push' to the AUR.
  --only NAME        Publish just one package (todo-flutter, habit-stack,
                     diet-guard-app).
  --poll SECONDS     How often to re-check /register (default: $POLL_SECONDS).
  -h, --help         Show this help.
EOF
    exit 0
}

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m  ! %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31m==> ERROR: %s\033[0m\n' "$*" >&2; exit 1; }

require_tools() {
    local missing=()
    local tool
    for tool in git makepkg updpkgsums namcap ssh python3 curl; do
        command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
    done
    if ((${#missing[@]})); then
        info "Installing missing tools: ${missing[*]}"
        # namcap/updpkgsums come from namcap + pacman-contrib; the rest are base.
        sudo pacman -S --needed --noconfirm namcap pacman-contrib git openssh python \
            || die "could not install: ${missing[*]}"
    fi
}

# ---------------------------------------------------------------------------
# Phase 1: wait for registration, then for the key to work
# ---------------------------------------------------------------------------

register_status() {
    python3 "$GATE" /register 2>/dev/null | head -1
}

open_browser() {
    local url="$1"
    local browser
    for browser in xdg-open thorium-browser chromium google-chrome-stable firefox librewolf; do
        if command -v "$browser" >/dev/null 2>&1; then
            "$browser" "$url" >/dev/null 2>&1 &
            info "Opened $url in $browser"
            return 0
        fi
    done
    warn "No browser found; open this yourself: $url"
}

ensure_key() {
    if [[ ! -f "$SSH_KEY" ]]; then
        log "Generating an AUR SSH key (none at $SSH_KEY)"
        ssh-keygen -t ed25519 -f "$SSH_KEY" -N '' -C 'kuhy@aur'
    fi
    if ! grep -q "Host $AUR_HOST" "$HOME/.ssh/config" 2>/dev/null; then
        log "Adding $AUR_HOST to ~/.ssh/config"
        mkdir -p "$HOME/.ssh"
        cat >> "$HOME/.ssh/config" <<EOF

# AUR uses a dedicated key so it stays separate from the GitHub identity.
Host $AUR_HOST
    User aur
    IdentityFile $SSH_KEY
    IdentitiesOnly yes
EOF
        chmod 600 "$HOME/.ssh/config"
    fi
}

ssh_works() {
    # The AUR refuses interactive shells; "Interactive shell is disabled" on a
    # successful key auth is the success signal, not an error.
    ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
        -o ConnectTimeout=15 "aur@$AUR_HOST" help 2>&1 |
        grep -qiE 'interactive shell is disabled|Welcome to AUR'
}

wait_for_registration() {
    local status
    status="$(register_status)"
    if [[ "$status" == "200" ]]; then
        log "AUR registration is OPEN"
    else
        log "AUR registration is closed (HTTP $status). Polling every ${POLL_SECONDS}s."
        info "Ctrl-C to stop; re-run any time, nothing is lost."
        while :; do
            sleep "$POLL_SECONDS"
            status="$(register_status)"
            if [[ "$status" == "200" ]]; then
                log "Registration is BACK (HTTP 200)"
                break
            fi
            printf '    %s still HTTP %s\n' "$(date +%H:%M)" "$status"
        done
    fi

    open_browser "https://$AUR_HOST/register"
    cat <<EOF

    ------------------------------------------------------------------
    Sign up, and paste this into the "SSH Public Key" field:

$(sed 's/^/      /' "$SSH_KEY.pub")

    You will need to confirm the address from your email before the
    account works. This script waits for that automatically.
    ------------------------------------------------------------------
EOF
}

wait_for_ssh() {
    log "Waiting for the SSH key to authenticate against the AUR"
    local waited=0
    until ssh_works; do
        sleep 30
        waited=$((waited + 30))
        if ((waited % 300 == 0)); then
            info "still waiting ($((waited / 60)) min) — key not accepted yet"
        fi
    done
    log "SSH authentication OK"
}

# ---------------------------------------------------------------------------
# Phase 2: build, verify and publish one package
# ---------------------------------------------------------------------------

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

publish_one() {
    local pkg="$1" repo="$2" wrapper="$3" binary="$4" expected="$5"
    local dir="$AUR_ROOT/$pkg"
    local version

    log "$pkg"

    [[ -d "$repo" ]] || { warn "$pkg: no repo at $repo"; return 1; }
    [[ -f "$dir/PKGBUILD" ]] || { warn "$pkg: no PKGBUILD at $dir"; return 1; }

    version="$(newest_tag "$repo")"
    [[ -n "$version" ]] || { warn "$pkg: no vX.Y.Z tag on the remote"; return 1; }
    info "newest release tag: v$version"

    cd "$dir"
    sed -i -E "s/^pkgver=.*/pkgver=$version/" PKGBUILD
    # The tarball for a tag contains the PKGBUILD, so the checksum can only be
    # computed after the tag exists — never committed ahead of time.
    updpkgsums >/dev/null 2>&1 || { warn "$pkg: updpkgsums failed (tag missing?)"; return 1; }

    info "building"
    if ! env PATH=/usr/bin:/bin:/usr/local/bin makepkg -Cf --noconfirm >/dev/null 2>&1; then
        warn "$pkg: makepkg failed"
        return 1
    fi

    local built
    built="$(find . -maxdepth 1 -name "$pkg-$version-*.pkg.tar.zst" | head -1)"
    [[ -n "$built" ]] || { warn "$pkg: no package produced"; return 1; }

    # namcap's "ELF files outside of a valid path ('opt/')" is a false positive
    # for /opt-installed apps, so only genuinely new errors are worth failing on.
    local findings
    findings="$(namcap "$built" 2>&1 | grep -E ' E: ' | grep -v "outside of a valid path" || true)"
    if [[ -n "$findings" ]]; then
        warn "$pkg: namcap errors:"
        printf '      %s\n' "$findings"
        return 1
    fi

    info "installing and launching"
    sudo pacman -U --noconfirm "$built" >/dev/null 2>&1 \
        || { warn "$pkg: pacman -U failed"; return 1; }
    verify_installed "$binary" "$expected" "$wrapper" || { warn "$pkg: launch check failed"; return 1; }

    # Generated before the rule check, which verifies it matches the PKGBUILD.
    makepkg --printsrcinfo > .SRCINFO
    check_aur_rules "$pkg" || return 1

    # The AUR repo is a separate remote living alongside the build dir; adding
    # it here (rather than cloning into a fresh path) keeps the verified
    # PKGBUILD and the thing being pushed byte-identical.
    if [[ ! -d .git ]]; then
        git init -q -b master .
        git remote add origin "ssh://aur@$AUR_HOST/$pkg.git"
    fi
    git remote get-url origin >/dev/null 2>&1 \
        || git remote add origin "ssh://aur@$AUR_HOST/$pkg.git"

    # Fetch first: an existing AUR package must be built on, not overwritten.
    if git fetch -q origin master 2>/dev/null; then
        git reset -q --soft FETCH_HEAD 2>/dev/null || true
    fi

    cat > .gitignore <<'EOF'
# Build products; the AUR tracks only the recipe.
*.pkg.tar.zst
*.tar.gz
src/
pkg/
EOF

    git add PKGBUILD .SRCINFO .gitignore
    if git diff --cached --quiet; then
        info "already up to date on the AUR; nothing to push"
        PUBLISHED+=("$pkg v$version (unchanged)")
        return 0
    fi

    git -c user.name='Krzysztof Rudnicki' \
        -c user.email='krzysztofrudnicki0@gmail.com' \
        commit -q -m "$pkg $version-1"

    if ((DRY_RUN)); then
        info "DRY RUN — not pushing"
        PUBLISHED+=("$pkg v$version (dry run)")
        return 0
    fi

    info "pushing to the AUR"
    git push -q origin master 2>&1 | tail -3 || { warn "$pkg: push failed"; return 1; }
    PUBLISHED+=("$pkg v$version")
    return 0
}

main() {
    require_tools
    [[ -f "$GATE" ]] || die "missing $GATE"
    mkdir -p "$AUR_ROOT"

    ensure_key
    if ((SKIP_WAIT)); then
        ssh_works || die "SSH key is not accepted yet; drop --skip-wait to wait for it"
    else
        wait_for_registration
        wait_for_ssh
    fi

    local entry pkg repo wrapper binary expected
    for entry in "${PACKAGES[@]}"; do
        IFS=: read -r pkg repo wrapper binary expected <<<"$entry"
        [[ -z "$ONLY" || "$ONLY" == "$pkg" ]] || continue
        if ! publish_one "$pkg" "$repo" "$wrapper" "$binary" "$expected"; then
            FAILED+=("$pkg")
        fi
    done

    log "Summary"
    if ((${#PUBLISHED[@]})); then
        printf '    published: %s\n' "${PUBLISHED[@]}"
    fi
    if ((${#FAILED[@]})); then
        printf '\033[1;31m    FAILED:    %s\033[0m\n' "${FAILED[@]}"
        info "Nothing broken was pushed; fix and re-run (safe to repeat)."
        return 1
    fi
    if ((${#PUBLISHED[@]} == 0)); then
        warn "nothing to do"
        return 1
    fi
    printf '\n    Check: https://aur.archlinux.org/packages/todo-flutter\n'
    return 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-wait) SKIP_WAIT=1; shift ;;
        --dry-run)   DRY_RUN=1; shift ;;
        --only)      ONLY="$2"; shift 2 ;;
        --poll)      POLL_SECONDS="$2"; shift 2 ;;
        -h|--help)   usage ;;
        *)           die "Unknown option: $1" ;;
    esac
done

main "$@"
