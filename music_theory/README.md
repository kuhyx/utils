# music_theory

Music theory from first principles, as typed Python you can hear. Follows
Luke Haas's ["Music Theory for Programmers"](https://runjs.app/blog/music-theory-for-programmers)
section by section: a sound is a number changing over time, pitch is
multiplicative, the tuning everyone wants cannot exist (3ⁿ ≠ 2ᵐ), so equal
temperament trades purity for a system that works in every key. Scales,
chords and progressions are then plain integer arrays on top of that, and a
small numpy synth turns them into WAV files.

Section-by-section notes, with what to listen for, live in
[`DOCS-article-walkthrough.md`](DOCS-article-walkthrough.md).

## Install

```
pip install "music_theory @ git+https://github.com/kuhyx/utils@music-theory-v0.1.0#subdirectory=music_theory"
```

Only dependency: numpy. Playback is left to `aplay` (or anything that opens
a 16-bit mono WAV); the package never touches an audio device itself.

## Hear the article

```
python -m music_theory list                       # every demo and its section
python -m music_theory explain comma              # just the numbers
python -m music_theory demo all --out /tmp/mt     # WAV per section + facts
aplay -q /tmp/mt/06_comma.wav
```

| demo | article section | what you hear |
|---|---|---|
| `tone` | 1 sound | A4, 440 Hz; the FFT peak is printed |
| `envelope` | 2 envelopes | same sine with a 10 ms then a 500 ms attack |
| `waveforms` | 2 timbre | sine, triangle, square, saw at 220 Hz |
| `octaves` | 3 octaves | A1 to A5, each double the last |
| `consonance` | 3 consonance | 2:1, 3:2, 4:3, 5:4, 16:15, then √2 |
| `comma` | 4 the comma | A4 against A4 × 1.0136, beating 6 times a second |
| `temperament` | 5 equal steps | twelve steps of 2^(1/12) |
| `divisions` | 5 why twelve | pure fifth vs the 5-, 7-, 12-, 19-, 24-TET fifth |
| `scale` | 6 scales | C major, then A minor |
| `modes` | 6 modes | seven rotations of the same array |
| `chords` | 7 qualities | major, minor, dim, aug, and three sevenths on C |
| `diatonic` | 8 keys | I ii iii IV V vi vii° of C |
| `transpose` | 8 transposition | I V vi IV in C, then +4 in E |
| `resolution` | 9 tension | V7 then I; the tritone collapses |
| `progressions` | 9 loops | pop, jazz, axis, fifties |
| `piece` | 11 the piece | bass + arpeggio + seeded melody, A minor |
| `bracket` | (beyond) | the same piece clean, then degraded |

## Render a recipe

A composition is data. `render` turns a recipe JSON into a loop-length WAV
and records its provenance (recipe, package version, SHA-256) in a manifest:

```json
{"key": "A3", "mode": "major", "tempo_bpm": 112, "progression": [1, 6, 3, 7],
 "bars": 16, "seed": 20260911, "waveform": "saw", "degrade": 0.0}
```

```
python -m music_theory render --recipe city.json --out city.wav --manifest MANIFEST.json
python -m music_theory render --recipe city.json --out ruin.wav --degrade 1.0 --manifest MANIFEST.json
```

`degrade` (0..1) is the same piece, ruined: past 0.5 the mode flips to its
darker relative, the tempo drags, melody notes drop out and drift off pitch,
and the signal is bit-crushed, hissed and low-passed. `degrade: 0` is byte-
identical to the original, so "the ending is the opening, destroyed" is a
one-flag transform on the same seed.

## Modules

| module | article | contents |
|---|---|---|
| `pitch` | 1, 5 | MIDI ↔ Hz (440·2^((n−69)/12)), cents, note names |
| `tuning` | 3, 4, 5 | harmonic series, just ratios, the comma, `best_divisions` |
| `scales` | 6 | step patterns, modes as rotations, `pitch_at_degree` |
| `chords` | 7, 9 | qualities, stacked thirds, Roman numerals, V7 → I |
| `progressions` | 8, 9 | named loops, degree → chord, transpose |
| `synth` | 1, 2 | waveforms, ADSR, low-pass, mix, normalise |
| `sequencer` | 10 | beat grid, `NoteEvent`, bar-exact render |
| `compose` | 11 | `Recipe` → bass, arpeggio, melody |
| `degrade` | — | the ruin transform |
| `analysis` | — | FFT peak and spectral centroid, so claims are testable |
| `wav`, `manifest` | — | 16-bit mono PCM out, SHA-256 provenance |

## Develop

```
pip install -r requirements.txt
python -m pytest            # 100 % branch coverage is enforced
pre-commit run --config music_theory/.pre-commit-config.yaml --all-files   # from the utils root
```

Consumed by `~/roadside-assistance` (`tools/render_music_beds.sh`) for its
three world-state music beds.
