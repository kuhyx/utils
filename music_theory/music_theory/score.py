# Copyright (c) 2026 Krzysztof Rudnicki
"""Score: a plain-text piece with named voices, noise drums and A/B sections.

Article section 10 treats notation as a serialization format; this is a
small one for text files. A ``Recipe`` generates its notes, a score spells
them out, and both render through the same sequencer. One directive per
line; a line starting with ``#`` is a comment::

    title waltz
    meter 3/4
    tempo 120
    seed 7
    voice lead wave=triangle vel=0.5
    voice drums noise vel=0.4
    section A bars=2
    lead: C5/2 E5/1 | G5/3
    drums: k . h . h . | k . s . h .
    play A A

``tempo`` counts quarter notes and ``/length`` is in quarter beats (default
1), so a 3/4 or 6/8 bar holds three. ``-`` is a rest. Drum steps are ``k``
kick, ``s`` snare, ``h`` hat or ``.``, one per eighth. ``play`` is optional
(default: sections in file order). A bar that does not add up to the meter
is an error naming the line, so a typo never shifts every later note.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING, ClassVar

from music_theory import score_tokens, sequencer, synth

if TYPE_CHECKING:
    from collections.abc import Callable

    from music_theory.score_tokens import Bar

DEFAULT_TEMPO = 120.0
DEFAULT_VELOCITY = 0.5


class ScoreError(ValueError):
    """A score that cannot be rendered; the message names the line."""


@dataclass(frozen=True)
class Voice:
    """A named part: pitched (one waveform) or a noise drum kit."""

    name: str
    noise: bool = False
    waveform: synth.Waveform = "triangle"
    velocity: float = DEFAULT_VELOCITY


@dataclass(frozen=True)
class Section:
    """A named run of bars; a voice with no lines in it rests."""

    name: str
    bars: int
    parts: dict[str, tuple[Bar, ...]]


@dataclass(frozen=True)
class Score:
    """A parsed score plus the text it came from (kept for the manifest)."""

    title: str
    meter: sequencer.Meter
    tempo_bpm: float
    seed: int
    sample_rate: int
    voices: tuple[Voice, ...]
    sections: tuple[Section, ...]
    order: tuple[str, ...]
    source: str

    def to_dict(self) -> dict[str, object]:
        """Manifest form: the full score text, which re-parses to this score."""
        return {"format": "score", "title": self.title, "text": self.source}


class _Parser:
    """Line-by-line state; ``finish`` checks what needs the whole file."""

    def __init__(self) -> None:
        self.title = ""
        self.meter = sequencer.Meter()
        self.tempo = DEFAULT_TEMPO
        self.seed = 0
        self.rate = synth.SAMPLE_RATE
        self.voices: dict[str, Voice] = {}
        ## (name, bars, header line, bars written so far per voice)
        self.sections: list[tuple[str, int, int, dict[str, list[Bar]]]] = []
        self.order: tuple[tuple[str, ...], int] | None = None

    def line(self, number: int, text: str) -> None:
        """Apply one non-comment line."""
        head, colon, tail = text.partition(":")
        if colon and len(head.split()) == 1:
            self._part(head.strip(), tail)
            return
        word, _, rest = text.partition(" ")
        if word not in self._HANDLERS:
            msg = f"unknown directive {word!r}"
            raise ValueError(msg)
        self._HANDLERS[word](self, number, rest.strip())

    def _set_title(self, _: int, rest: str) -> None:
        self.title = rest

    def _set_tempo(self, _: int, rest: str) -> None:
        self.tempo = score_tokens.positive(rest, "tempo")

    def _set_seed(self, _: int, rest: str) -> None:
        self.seed = score_tokens.count(rest, "seed", 0)

    def _set_rate(self, _: int, rest: str) -> None:
        self.rate = score_tokens.count(rest, "rate", 1)

    def _set_meter(self, _: int, rest: str) -> None:
        if self.sections:
            msg = "meter must come before the first section"
            raise ValueError(msg)
        self.meter = sequencer.Meter.parse(rest)

    def _voice(self, _: int, rest: str) -> None:
        name, *options = rest.split() or [""]
        if not name:
            msg = "voice needs a name"
            raise ValueError(msg)
        if name in self.voices:
            msg = f"duplicate voice {name!r}"
            raise ValueError(msg)
        settings = dict(option.partition("=")[::2] for option in options)
        noise = "noise" in options
        if noise:
            del settings["noise"]
        if set(settings) - {"wave", "vel"} or "" in settings.values():
            msg = f"unknown voice option in {rest!r}; use noise, wave=, vel="
            raise ValueError(msg)
        if noise and "wave" in settings:
            msg = "a noise voice takes no wave="
            raise ValueError(msg)
        waveform = score_tokens.waveform(settings.get("wave", "triangle"))
        velocity = score_tokens.positive(
            settings.get("vel", str(DEFAULT_VELOCITY)), "vel"
        )
        self.voices[name] = Voice(name, noise, waveform, velocity)

    def _section(self, number: int, rest: str) -> None:
        name, _, bars = rest.partition(" bars=")
        if not name or not bars:
            msg = "section needs a name and bars=N"
            raise ValueError(msg)
        if any(name == known for known, *_ in self.sections):
            msg = f"duplicate section {name!r}"
            raise ValueError(msg)
        self.sections.append((name, score_tokens.count(bars, "bars", 1), number, {}))

    def _play(self, number: int, rest: str) -> None:
        if not rest:
            msg = "play needs at least one section name"
            raise ValueError(msg)
        self.order = (tuple(rest.split()), number)

    def _part(self, name: str, rest: str) -> None:
        if not self.sections:
            msg = "part outside a section"
            raise ValueError(msg)
        if name not in self.voices:
            msg = f"unknown voice {name!r}"
            raise ValueError(msg)
        step = score_tokens.drum_step if self.voices[name].noise else score_tokens.note
        bars = self.sections[-1][3].setdefault(name, [])
        expected = self.meter.beats_per_bar
        for bar_text in rest.strip().strip("|").split("|"):
            measure = tuple(step(token) for token in bar_text.split())
            got = sum(length for _, length in measure)
            if not math.isclose(got, expected):
                msg = (
                    f"voice {name} bar {len(bars) + 1}: "
                    f"expected {expected:g} beats, got {got:g}"
                )
                raise ValueError(msg)
            bars.append(measure)

    _HANDLERS: ClassVar[dict[str, Callable[[_Parser, int, str], None]]] = {
        "title": _set_title,
        "meter": _set_meter,
        "tempo": _set_tempo,
        "seed": _set_seed,
        "rate": _set_rate,
        "voice": _voice,
        "section": _section,
        "play": _play,
    }

    def finish(self, source: str) -> Score:
        """Check bar counts and play order, then build the ``Score``."""
        if not self.sections:
            msg = "score has no sections"
            raise ScoreError(msg)
        for name, count, number, parts in self.sections:
            for voice, bars in parts.items():
                if len(bars) != count:
                    msg = (
                        f"line {number}: section {name}: voice {voice} has "
                        f"{len(bars)} bars, expected {count}"
                    )
                    raise ScoreError(msg)
        names = tuple(name for name, *_ in self.sections)
        order, number = self.order or (names, 0)
        for name in order:
            if name not in names:
                msg = f"line {number}: unknown section {name!r}"
                raise ScoreError(msg)
        sections = tuple(
            Section(name, count, {v: tuple(b) for v, b in parts.items()})
            for name, count, _, parts in self.sections
        )
        return Score(
            self.title,
            self.meter,
            self.tempo,
            self.seed,
            self.rate,
            tuple(self.voices.values()),
            sections,
            order,
            source,
        )


def parse(text: str) -> Score:
    """Parse score text; every error is a ``ScoreError`` naming its line."""
    parser = _Parser()
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            parser.line(number, line)
        except ValueError as error:
            msg = f"line {number}: {error}"
            raise ScoreError(msg) from error
    return parser.finish(text)
