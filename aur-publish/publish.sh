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

# The rest lives in lib/, sourced (not executed) so every function sees the
# readonly config above and the mutable FAILED/PUBLISHED arrays main() reads.
# shellcheck source=lib/aur_registration.sh
source "$SCRIPT_DIR/lib/aur_registration.sh"
# shellcheck source=lib/aur_verify.sh
source "$SCRIPT_DIR/lib/aur_verify.sh"
# shellcheck source=lib/aur_publish_one.sh
source "$SCRIPT_DIR/lib/aur_publish_one.sh"

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
