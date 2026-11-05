"""omniroute-gateway: keep the local OmniRoute gateway up, checked and current.

  start   (re)create the container on the pinned image and wait for its API
  health  real chat probe + fix ladder (systemd timer, every 10 min)
  update  backup + newest stable tag with rollback (systemd timer, weekly)
  backup  stop, tar the data volume, start
  combo   rebuild free-best from ~/.config/omniroute/order.tsv
Instance: OMNIROUTE_NAME / OMNIROUTE_VOLUME / OMNIROUTE_PORT (default: live).
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from omniroute_offload import _gw_api as api
from omniroute_offload import _gw_combo as combo
from omniroute_offload import _gw_docker as dock
from omniroute_offload import _gw_health as health
from omniroute_offload import _gw_update as update
from omniroute_offload._gw_config import Config

if TYPE_CHECKING:
    from collections.abc import Callable


def _start(cfg: Config) -> int:
    dock.recreate(cfg, cfg.image(), health.secret(cfg, "admin_password"))
    if health.wait_up(cfg):
        print(f"omniroute up: {cfg.base_url} ({cfg.image()})")
        return 0
    print(f"{cfg.name} did not come up; see: docker logs {cfg.name}", file=sys.stderr)
    return 1


def _backup(cfg: Config) -> int:
    print(dock.backup(cfg, cfg.image().rsplit(":", 1)[-1]))
    return 0


def _combo(cfg: Config) -> int:
    return 0 if combo.refresh(cfg) else 1


def main(argv: list[str] | None = None) -> int:
    """Run one subcommand; non-zero on failure."""
    parser = argparse.ArgumentParser(
        prog="omniroute-gateway",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command", choices=["start", "health", "update", "backup", "combo"]
    )
    args = parser.parse_args(argv)
    cfg = Config.from_env()
    actions: dict[str, Callable[[Config], int]] = {
        "start": _start,
        "health": health.run,
        "update": update.run,
        "backup": _backup,
        "combo": _combo,
    }
    try:
        return actions[args.command](cfg)
    except (dock.DockerError, api.ApiError, OSError) as err:
        print(f"omniroute-gateway {args.command}: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
