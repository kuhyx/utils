# Add a plain-text multi-voice score format

## what
Add a plain-text score format that `compose.py` and `sequencer.py` can
render: named voices, a noise-drum voice, a `meter` field (3/4, 6/8) and
A/B sections. Today `sequencer.BEATS_PER_BAR` is fixed at 4 and a `Recipe`
has one bass, one arpeggio and one melody.
Source: simonwillison.net/2026/Oct/6/scrimshaw-jukebox.

## done
```
cd ~/src/utils/music_theory && PYTHONPATH=. python -m pytest music_theory/tests/test_score.py music_theory/tests/test_sequencer.py music_theory/tests/test_compose.py --cov=music_theory.score --cov=music_theory.sequencer --cov=music_theory.compose --cov-branch --cov-fail-under=100
```
exits 0. It covers: a 3/4 and a 6/8 score render bar-exact loops, two named
voices stack, the noise-drum voice is deterministic for a fixed seed, and an
A/B-section score renders A then B in order.

## verify
Desktop. Render one 3/4 and one 6/8 example score with
`PYTHONPATH=. python -m music_theory render --score examples/waltz.txt --out /tmp/waltz.wav`,
check `analysis.dominant_frequency` and the frame count equal
`sequencer.loop_frames` for the bar count, and re-render for byte-identical
output. The final listen is kuhy's.

## read first
- `music_theory/compose.py` (`Recipe`), `music_theory/sequencer.py`
  (`NoteEvent`, `BEATS_PER_BAR`), `music_theory/noise.py` (drum source).
- `DOCS-article-walkthrough.md` (article section 10, notation as format).
- `~/.claude/skills/procedural-music/SKILL.md`.

REMOVE ME AFTER FINISH
