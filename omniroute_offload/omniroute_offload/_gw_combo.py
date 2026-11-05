"""Rebuild the free-best combo from the benchmark's order.tsv in conf_dir.

Keeps tool-capable models with a big enough prompt window and Tetris score, in
the file's rank order (the combo is a priority chain).
"""

from __future__ import annotations

import csv
import sys
from typing import TYPE_CHECKING

from omniroute_offload import _gw_api as api
from omniroute_offload import _gw_health as health

if TYPE_CHECKING:
    from pathlib import Path

    from omniroute_offload._gw_config import Config

MIN_PROMPT = 16_000
MIN_TETRIS = 0.85


def ranked_models(order: Path) -> list[str]:
    """Return agent-capable models from order.tsv that pass the filters, best first."""
    with order.open(newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return [
        row["model"]
        for row in rows
        if row.get("tools") == "yes"
        and row.get("tetris", "-") != "-"
        and float(row["tetris"]) >= MIN_TETRIS
        and float(row.get("max_prompt") or 0) >= MIN_PROMPT
    ]


def refresh(cfg: Config) -> bool:
    """Upsert the combo; log and return False when order.tsv is missing or empty."""
    order = cfg.conf_dir / "order.tsv"
    if not order.exists():
        print(f"combo kept: no {order}", file=sys.stderr)
        return False
    models = ranked_models(order)
    if not models:
        print(f"combo kept: no model in {order} passes the filter", file=sys.stderr)
        return False
    admin = api.Admin(cfg, health.secret(cfg, "admin_password"))
    admin.upsert_combo(api.COMBO, models)
    print(f"{api.COMBO}: {' > '.join(models)}", file=sys.stderr)
    return True
