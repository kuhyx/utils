# game_recording

Session recorder for a game, as a package (import name `game_recording`, not
published to PyPI, stdlib only). It needs Python 3.14 or newer
(`requires-python` in `pyproject.toml`). It records a person's own dev play from
outside the game (so the game's frame time stays untouched) and stamps the
game's telemetry moments onto the video as events and MKV chapters.

- Starts the game as a child process, finds its X11 window by pid (`xdotool`),
  records it with `gpu-screen-recorder` (else `ffmpeg` x11grab) plus the audio
  monitor, and stops the recorder with SIGINT when the game exits.
- A window that goes away and returns (an i3 workspace switch) starts a new
  part file; every part sits on one timeline.
- `finalize` writes `<session>.events.json` next to the video and remuxes
  chapters in without re-encoding. `latest`, `list` and `open N` show moments
  and open the video in `mpv` three seconds before one.
- Recording trouble never changes the game's exit code or stops the game.
- Bots, tests, headless and muted runs are never recorded.

Needs `ffmpeg`, `ffprobe`, `xdotool` and, optionally, `gpu-screen-recorder`.

Consume via:
```
game_recording @ git+https://github.com/kuhyx/utils@game-recording-v0.1.1#subdirectory=game_recording
```

## Configure it for a game

The package knows no game. One `Config` carries everything game-specific; the
game's own entry script (a few lines) builds it and calls `cli.main`:

```python
import sys

from game_recording import Config, MomentMap, cli
from game_recording.config import COMMON_DIRECT

CONFIG = Config(
    binaries_dir="data/my-game_binaries",  # under $HOME; feedback/ lives inside
    env_prefix="MYGAME",  # MYGAME_NO_RECORD, MYGAME_FEEDBACK_DIR, ...
    moments=MomentMap(
        direct={**COMMON_DIRECT, "buy": ("item", "cost")},
        passthrough_prefixes=("sim_", "milestone"),
    ),
)

if __name__ == "__main__":
    sys.exit(cli.main(sys.argv[1:], CONFIG))
```

| Field | Meaning |
| --- | --- |
| `Config.binaries_dir` | The game's binaries folder, relative to `$HOME`. Default feedback dir: `<binaries_dir>/feedback`; recordings go in its `recordings/`. |
| `Config.env_prefix` | Variables derive from it: `<P>_NO_RECORD` (`1` = never record), `<P>_FEEDBACK_DIR` (any value = never record), `<P>_BINARIES` (binaries folder override), `<P>_RECORDER_BACKEND` (`auto`, `gsr`, `x11grab`), `<P>_RECORDER_NICE` (default 10). |
| `Config.binaries_env` | Overrides the `<P>_BINARIES` variable name. |
| `Config.extra_blocking_flags` | More environment flags that switch recording off at `1`. |
| `Config.bot_args` | Game args that mark a bot or test run (default `--autodrive`, `--result-file=`, `--expect-window=`, `--screenshot-dir=`, `--save-dir=`). |
| `MomentMap.direct` | Event name to the fields kept; one telemetry line is one moment. Default `COMMON_DIRECT`. |
| `MomentMap.passthrough_prefixes` | Events starting with these are moments as they are. |
| `MomentMap.game_end_fields`, `error_kinds`, `hitch_merge_s` | Fields of a `game_end` moment, the `engine_error` kinds that count, and the merge window of a hitch burst. |
| `MomentMap.classifiers` | Extra per-line rules `(row) -> moment or None`, tried first. Build moments with `moments.moment(row, kind, label, **extra)`. |
| `MomentMap.session_rules` | Extra rules `(rows) -> moments` for moments that need several lines (a stall, a repeated failure). |

## Contract with the game

- The game is started with `--session-id=<id>` and `--feedback-dir=<dir>`
  appended to its user args (after `--`); a recorded run needs `--dev`.
- It writes `<feedback-dir>/feedback.jsonl`, one JSON object per line with
  `session`, `event`, `seq` and `ms` (its own clock). One `recording_sync`
  line (`ms` plus `unix` or `unix_us`) pins that clock to unix time.
- Output layout: `<feedback-dir>/recordings/<session>.mkv` (`.partN.mkv` for
  later parts), `.rec.json`, `.events.json`, `.ffmpeg.log`.

## CLI

```
wrap [--session ID] [--force] [--audio default|lavfi|SRC] [--fps N] [--max-seconds S] -- <game command>
finalize <session>.rec.json
latest | list [--dir D] [--session ID]
open [N] [--dir D] [--session ID] [--dry-run]
```

## Develop

```
pip install -r requirements.txt
python -m pytest --cov=game_recording        # 100 % branch coverage required
pre-commit run --config game_recording/.pre-commit-config.yaml --all-files   # from the utils root
```

Version 0.1.1; the tag is `game-recording-v0.1.1`.
