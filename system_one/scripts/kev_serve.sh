#!/bin/bash
# ============================================================================
# Serve one Kev checkpoint on a loopback port (foreground; systemd ExecStart).
#   kev_serve.sh <checkpoint> <port>   e.g. kev_serve.sh jaredpalmer/kev-4b@v1.0 8018
# Refuses to load while a game runs or VRAM is short (system_one.guard), so a
# socket-activated start can never take the GPU from a game.
# ============================================================================

set -euo pipefail

readonly KEV_DIR="${KEV_DIR:-$HOME/vendor/kev}"
readonly SYSTEM_ONE_DIR="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
    echo "Usage: $(basename "$0") <checkpoint> <port> [need_mib]" >&2
    exit 2
}

main() {
    [[ $# -ge 2 ]] || usage
    local checkpoint="$1" port="$2" need_mib="${3:-16000}"
    if ! PYTHONPATH="$SYSTEM_ONE_DIR" python3 -m system_one.guard "$need_mib"; then
        echo "kev_serve: GPU not available, not loading $checkpoint" >&2
        exit 75  # EX_TEMPFAIL
    fi
    cd "$KEV_DIR"
    # KEV_VRAM_MIB (set by the unit) = hard VRAM budget via kev_launch.py.
    local -a entry=(-m kev.serve)
    [[ -n "${KEV_VRAM_MIB:-}" ]] && entry=("$SYSTEM_ONE_DIR/system_one/kev_launch.py")
    exec uv run --frozen --extra serve python "${entry[@]}" \
        --run "$checkpoint" --host 127.0.0.1 --port "$port"
}

main "$@"
