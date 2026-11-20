#!/bin/bash

# ============================================================================
# Local System One (Jev-compatible) decision engines: install everything.
#
#   Kev 1.0 (jaredpalmer/kev @ kev-1.0)   -> ~/vendor/kev, uv env, TypeSafe API
#   SemIf   (TheoLeeCJ/SemIf-OpenJev @ pin) -> ~/vendor/semif, own venv
#   Laya 0.4.1 (PyPI)                       -> own venv
#   systemd user units: 127.0.0.1:8008 starts Kev-4B on demand, idle-stops
#   jevgrep 0.8.0 (pnpm, bin in ~/.local/bin), auth = LOCAL endpoint only
#
# Nothing here talks to a paid API: jevgrep is pointed at the loopback Kev and
# no TypeSafe/OpenRouter/Vercel key is ever written. Idempotent; rerun freely.
# ============================================================================

set -euo pipefail

readonly HERE="$(cd "$(dirname "$0")" && pwd)"
readonly VENDOR="$HOME/vendor"
readonly VENVS="$HOME/.local/share/system_one/venvs"
readonly UNITS="$HOME/.config/systemd/user"
readonly KEV_REF="kev-1.0"
readonly SEMIF_REF="23cf1f3"
readonly LAYA_VERSION="0.4.1"
readonly JEVGREP_VERSION="0.8.0"
readonly CAPPED="$HOME/.claude/scripts/capped.sh"

log() { printf '[system_one] %s\n' "$*"; }

capped() {
    if [[ -x "$CAPPED" ]]; then CAP_MEM=4G CAP_CPU_PCT=20 "$CAPPED" "$@"; else "$@"; fi
}

clone_at() {
    local url="$1" dir="$2" ref="$3"
    if [[ ! -d "$dir/.git" ]]; then
        git clone -q "$url" "$dir"
    fi
    git -C "$dir" fetch -q --tags origin
    git -C "$dir" -c advice.detachedHead=false checkout -q "$ref"
}

ensure_tools() {
    local missing=()
    for tool in git uv curl pnpm node nvidia-smi; do
        command -v "$tool" >/dev/null || missing+=("$tool")
    done
    if ((${#missing[@]})); then
        log "installing: ${missing[*]}"
        sudo pacman -S --needed --noconfirm git uv curl pnpm nodejs nvidia-utils
    fi
}

install_kev() {
    clone_at https://github.com/jaredpalmer/kev.git "$VENDOR/kev" "$KEV_REF"
    (cd "$VENDOR/kev" && capped uv sync --frozen --extra serve)
}

install_semif() {
    clone_at https://github.com/TheoLeeCJ/SemIf-OpenJev.git "$VENDOR/semif" "$SEMIF_REF"
    [[ -d "$VENVS/semif" ]] || uv venv -q -p 3.13 "$VENVS/semif"
    capped uv pip install -q --python "$VENVS/semif/bin/python" -e "$VENDOR/semif[llamacpp]"
}

install_laya() {
    [[ -d "$VENVS/laya" ]] || uv venv -q -p 3.13 "$VENVS/laya"
    capped uv pip install -q --python "$VENVS/laya/bin/python" "laya[serve]==$LAYA_VERSION"
}

install_units() {
    mkdir -p "$UNITS"
    for unit in "$HERE"/systemd/*; do
        ln -sf "$unit" "$UNITS/$(basename "$unit")"
    done
    systemctl --user daemon-reload
    systemctl --user enable --now system-one-kev.socket
}

install_jevgrep() {
    pnpm add -g --config.global-bin-dir="$HOME/.local/bin" "@dzhng/jevgrep@$JEVGREP_VERSION" >/dev/null
    # Kev ignores the key; jevgrep requires one. Local endpoint only.
    printf 'local\n' | "$HOME/.local/bin/jg" auth --provider custom \
        --base-url http://127.0.0.1:8008/v1 --model kev-latest --stdin
}

main() {
    mkdir -p "$VENDOR" "$VENVS"
    ensure_tools
    log "Kev";      install_kev
    log "SemIf";    install_semif
    log "Laya";     install_laya
    log "units";    install_units
    log "jevgrep";  install_jevgrep
    log "done: curl -s http://127.0.0.1:8008/v1/models"
}

main "$@"
