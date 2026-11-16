# Copyright (c) 2026 Krzysztof Rudnicki
"""What a game tells the recorder: its names, its blockers, its telemetry vocabulary.

The package knows nothing about any one game. A game builds one `Config` and
hands it to `game_recording.cli.main` (see the README for the whole surface).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

type Row = dict[str, Any]
"""One telemetry line, as the game wrote it."""
type Moment = dict[str, Any]
"""One timestamped moment built from telemetry."""
type Classifier = Callable[[Row], Moment | None]
"""Turns one telemetry line into a moment, or None when it is not one."""
type SessionRule = Callable[[list[Row]], list[Moment]]
"""Finds the moments that need several telemetry lines."""

# Entries any dev telemetry has: a moment as they are, with the fields worth keeping.
COMMON_DIRECT: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "session_start": (),
        "hub_open": (),
        "pause_open": (),
        "pause_close": ("paused_s",),
        "quit": ("reason",),
        "session_end": ("reason", "elapsed_s"),
    }
)

# Game args that only a bot or a test run carries.
BOT_ARGS = (
    "--autodrive",
    "--result-file=",
    "--expect-window=",
    "--screenshot-dir=",
    "--save-dir=",
)


@dataclass(frozen=True)
class MomentMap:
    """Which telemetry entries are moments worth a timestamp.

    Attributes:
        direct: event name -> the fields kept; one entry is one moment.
        passthrough_prefixes: events starting with these are moments as they are.
        game_end_fields: the fields of a `game_end` moment.
        error_kinds: `engine_error` kinds that are a moment (warnings are noise).
        hitch_merge_s: `hitch` entries closer than this are one moment.
        classifiers: extra per-entry rules, tried before the built-in ones.
        session_rules: extra rules over the whole session, added to the hitch burst.
    """

    direct: Mapping[str, tuple[str, ...]] = COMMON_DIRECT
    passthrough_prefixes: tuple[str, ...] = ()
    game_end_fields: tuple[str, ...] = ("outcome", "elapsed_s")
    error_kinds: frozenset[str] = frozenset({"error", "script_error", "shader_error"})
    hitch_merge_s: float = 2.0
    classifiers: tuple[Classifier, ...] = ()
    session_rules: tuple[SessionRule, ...] = ()


@dataclass(frozen=True)
class Config:
    """One game's recorder settings.

    Attributes:
        binaries_dir: the game's binaries folder, relative to $HOME; its
            `feedback/` folder holds the telemetry and the recordings.
        env_prefix: prefix of the game's environment variables, e.g. `GAME` for
            `GAME_NO_RECORD`, `GAME_FEEDBACK_DIR`, `GAME_RECORDER_BACKEND`,
            `GAME_RECORDER_NICE` and `GAME_BINARIES`.
        moments: the telemetry-to-moment map.
        bot_args: game args that mark a bot or test run (never recorded).
        extra_blocking_flags: more env flags that switch recording off at "1".
        binaries_env: overrides the `<prefix>_BINARIES` variable name.
    """

    binaries_dir: str
    env_prefix: str
    moments: MomentMap = field(default_factory=MomentMap)
    bot_args: tuple[str, ...] = BOT_ARGS
    extra_blocking_flags: tuple[str, ...] = ()
    binaries_env: str = ""

    def env_name(self, suffix: str) -> str:
        """The game's environment variable `<prefix>_<suffix>`."""
        return f"{self.env_prefix}_{suffix}"

    @property
    def blocking_flags(self) -> tuple[str, ...]:
        """Env flags that count only as "1" and switch recording off."""
        return (self.env_name("NO_RECORD"), *self.extra_blocking_flags)

    @property
    def binaries_var(self) -> str:
        """The variable that names the binaries folder."""
        return self.binaries_env or self.env_name("BINARIES")
