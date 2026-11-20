"""Start ``kev.serve`` under a hard VRAM budget (run with Kev's own venv python).

    KEV_VRAM_MIB=15000 python kev_launch.py --run jaredpalmer/kev-4b@v1.0 --port 8018

Kev's prefix cache and PyTorch's caching allocator let an idle-looking server
grow to the whole 24 GB under long jevgrep states. A per-process memory
fraction makes the allocator release its cache and retry before it grows past
the budget; a request that still does not fit fails with a 500 (the caller
falls back) instead of starving a game. Torch only, no third-party deps here.
"""

from __future__ import annotations

import os
import runpy
import sys

import torch  # type: ignore[import-not-found]


def main() -> None:
    """Apply the budget, then hand over to kev.serve with the same argv."""
    budget = int(os.environ.get("KEV_VRAM_MIB", "0"))
    if budget and torch.cuda.is_available():
        total = torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(min(1.0, budget * 2**20 / total), 0)
        print(f"kev_launch: VRAM budget {budget} MiB", file=sys.stderr)
    sys.argv[0] = "kev.serve"
    runpy.run_module("kev.serve", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
