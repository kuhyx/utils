# Copyright (c) 2026 Krzysztof Rudnicki
"""Session recorder for a game: records a dev run beside it, stamps telemetry moments on the video.

A game configures it with one `Config` (names, blockers, telemetry vocabulary)
and calls `game_recording.cli.main`. See the package README for the whole surface.
"""

from game_recording.config import Config, MomentMap

__version__ = "0.1.0"
__all__ = ["Config", "MomentMap", "__version__"]
