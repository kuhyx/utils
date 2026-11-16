# Copyright (c) 2026 Krzysztof Rudnicki
"""Shared fixtures for the recorder tests: a made-up game's config and telemetry lines."""

from game_recording import moments
from game_recording.config import COMMON_DIRECT, Config, Moment, MomentMap, Row

SESSION = "1794396071-c6df"
# The game's clock: `ms` counts from the log's creation; the sync entry pairs one
# ms value with the unix time of that same instant.
SYNC_UNIX = 1_800_000_000.250
SYNC_MS = 200

MOMENT_MAP = MomentMap(
    direct={
        **COMMON_DIRECT,
        "buy": ("buff", "bought", "cost"),
        "game_start": ("loadout", "cost", "men", "seed"),
        "command": ("order", "pos"),
        "lab_result": ("wins", "runs", "mean_seconds"),
        "reset_progress": ("files",),
    },
    passthrough_prefixes=("evt_", "milestone"),
)
CONFIG = Config(binaries_dir="data/demo_binaries", env_prefix="DEMO", moments=MOMENT_MAP)


def entry(event: str, ms: int, seq: int = 0, **fields: object) -> Row:
    """One telemetry line as the game writes it."""
    return {
        "event": event,
        "session": SESSION,
        "seq": seq,
        "ms": ms,
        "frame": ms // 16,
        "time": "2026-11-11T12:00:00",
        **fields,
    }


def sync_entry() -> Row:
    """The line that pairs the game clock with unix time."""
    return entry("recording_sync", SYNC_MS, 1, unix=SYNC_UNIX)


def classify_one(row: Row, moment_map: MomentMap = MOMENT_MAP) -> Moment | None:
    """The one moment a line becomes, None when it is not one."""
    found = moments.classify([row], moment_map)
    return found[0] if found else None
