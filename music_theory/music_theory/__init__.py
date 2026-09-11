# Copyright (c) 2026 Krzysztof Rudnicki
"""Music theory from first principles, as code.

Follows Luke Haas's "Music Theory for Programmers"
(https://runjs.app/blog/music-theory-for-programmers) section by section:
a sound is a number changing over time, pitch is multiplicative, the tuning
everyone wants cannot exist, so equal temperament trades purity for a
system that works in every key. Scales, chords and progressions are then
plain arrays of integers on top of that.

Every module is pure and typed; ``synth``/``sequencer``/``compose`` turn
the integers into audio with numpy so each idea can be heard, not just read.
"""

from __future__ import annotations

__version__ = "0.1.0"
