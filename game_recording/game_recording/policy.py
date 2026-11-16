# Copyright (c) 2026 Krzysztof Rudnicki
"""When a run is recorded: a person's own dev play, never bots, tests or headless runs."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from game_recording.config import Config

DEV_ARG = "--dev"
NO_DEV_ARG = "--no-dev"
# (engine flag, the value after it that makes the run headless or muted)
ENGINE_BLOCKERS = (("--display-driver", "headless"), ("--audio-driver", "Dummy"))


@dataclass(frozen=True)
class Decision:
    """Whether to record, and the reason either way."""

    record: bool
    reason: str


def arg_value(args: Sequence[str], prefix: str) -> str:
    """The value of the first `<prefix>value` argument, "" when absent."""
    for arg in args:
        if arg.startswith(prefix):
            return arg[len(prefix) :]
    return ""


def _engine_blocker(args: Sequence[str]) -> str:
    """Why the engine arguments (before `--`) make this a headless or muted run."""
    engine = list(args[: args.index("--")]) if "--" in args else list(args)
    if "--headless" in engine:
        return "--headless"
    for flag, value in ENGINE_BLOCKERS:
        if flag in engine and engine[engine.index(flag) + 1 : engine.index(flag) + 2] == [value]:
            return f"{flag} {value}"
    return ""


def _env_blocker(env: Mapping[str, str], config: Config) -> str:
    """Why the environment opts out: a flag is on only as "1"; a feedback dir is a path, any value counts."""
    for name in config.blocking_flags:
        if env.get(name) == "1":
            return f"{name}=1"
    path = config.env_name("FEEDBACK_DIR")
    return f"{path} is set" if env.get(path) else ""


def _args_blocker(args: Sequence[str], config: Config) -> str:
    """Why the game's own arguments say this is not dev play."""
    if NO_DEV_ARG in args or DEV_ARG not in args:
        return "not a --dev run"
    for marker in config.bot_args:
        hit = next((a for a in args if a.startswith(marker)), "")
        if hit:
            return f"bot or test run ({hit})"
    blocker = _engine_blocker(args)
    return f"headless or muted run ({blocker})" if blocker else ""


def decide(args: Sequence[str], env: Mapping[str, str], config: Config, *, force: bool = False) -> Decision:
    """Record only a windowed dev run on a real display; `force` is for tests."""
    if not env.get("DISPLAY"):
        return Decision(record=False, reason="no DISPLAY")
    if force:
        return Decision(record=True, reason="forced")
    reason = _env_blocker(env, config) or _args_blocker(args, config)
    if reason:
        return Decision(record=False, reason=reason)
    return Decision(record=True, reason="dev play")
