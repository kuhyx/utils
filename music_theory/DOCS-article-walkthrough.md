# The article, section by section, as code

Each row: the article's claim, where it lives here, and the demo that lets
you hear it. Run `python -m music_theory demo all --out /tmp/mt` once and
follow along with `aplay`.

## 1. Sound is a number that changes over time

A note is a frequency in Hz. Pitch perception is multiplicative: "one
semitone up" means "multiply by 2^(1/12)", never "add N Hz".
`pitch.midi_to_hz` is that exponent counted from A4 = 440 Hz.
Demo `tone`; `analysis.dominant_frequency` confirms the FFT peak is 440.

## 2. Envelopes and timbre

Volume over time (attack, decay, sustain, release) is what makes a sound a
note. A 10 ms attack reads as struck, 500 ms as bowed; the release is what
stops a click at the end. `synth.Envelope` + `synth.adsr`. Timbre is the
recipe of overtones at 2×, 3×, 4× the fundamental; sine, triangle, square
and saw are four such recipes (`synth.oscillator`). Demos `envelope`,
`waveforms`; the printed spectral centroid rises from sine to saw.

## 3. Octaves and consonance

Doubling the frequency gives the "same" note (`octaves`). Two notes sound
consonant when their ratio is simple: for p/q the combined wave repeats
after q cycles of the lower note (`tuning.repeat_cycles`), so 3/2 locks in
after 2 cycles, 16/15 after 15, and √2 (the tritone) never. Demo
`consonance`.

## 4. The Pythagorean comma

Stack twelve pure fifths and you overshoot seven octaves by
(3/2)¹² / 2⁷ = 1.013643, about 23.5 cents. The proof is one line: 3ⁿ = 2ᵐ
has no integer solution because both are prime. "The system we want does
not exist and never has." `tuning.pythagorean_comma`; demo `comma` plays
A4 against A4 × comma and you hear it beat six times a second.

## 5. Equal temperament, and why twelve

Split the octave into twelve equal multiplicative steps. Every interval
except the octave is slightly wrong, but wrong by the same amount in every
key. The fifth becomes 2^(7/12) = 1.498307, 0.113 % flat.
`tuning.best_divisions` brute-forces every division up to 25: twelve is the
smallest whose fifth is within 0.2 % of 3/2 (`first_acceptable_division`).
Demos `temperament`, `divisions`.

## 6. Scales

A scale is a subset of the twelve notes with UNEVEN gaps, so the ear can
tell where it is. Encode it as the step array: major `[2,2,1,2,2,2,1]`,
minor `[2,1,2,2,1,2,2]`. `scales.build(60, major)` is the article's
`reduce` → `[60,62,64,65,67,69,71,72]`. All seven modes are the same array
rotated (`scales.mode`); aeolian is rotation 5 and equals natural minor.
Demos `scale`, `modes`.

## 7. Chords

Stack every other scale degree (`chords.stacked_thirds`). Major triad
`[0,4,7]`, minor `[0,3,7]`: one array element is the entire happy/sad
difference. Sevenths add one more third. Demo `chords`.

## 8. Keys and Roman numerals

Build a triad on each degree and you get the diatonic chords of the key:
C major → C Dm Em F G Am B° (`chords.diatonic_chords`). Roman numerals are
relative addressing, so `progressions.transpose` is adding one constant to
every MIDI number. Demos `diatonic`, `transpose`.

## 9. Tension and resolution

V7 contains the leading tone (B in C) and a tritone (B–F). Both resolve by
a single semitone into the tonic: B→C, F→E, contrary motion, the tritone
collapsing into a major third. `chords.resolution` returns exactly those
two moves. Common loops (I V vi IV, ii V I, vi IV I V, I vi IV V) are in
`progressions.NAMED`. Demos `resolution`, `progressions`.

## 10. Notation as a serialization format

The staff is diatonic, not chromatic; sharps and flats are the escape
hatch; durations are powers of two and a dot multiplies by 1.5; tempo
turns beats into seconds. Here that is `sequencer.NoteEvent` (pitch, start
beat, length in beats) and `sequencer.beat_seconds`. No demo; the
sequencer is what every later demo renders through.

## 11. The complete composition

Pick a key and a progression, play the root as bass, the chord tones as an
arpeggio, and a melody drawn from the scale. Constraining every voice to
the scale is what makes any melody fit. `compose.Recipe` +
`compose.compose`, seeded so the same recipe always renders the same bytes.
Demo `piece`.

## Beyond the article: degrade

If the piece is data, "the ending is the opening, destroyed" is a transform
on that data. `degrade` darkens the mode past 0.5, drags the tempo, thins
and detunes the melody, then bit-crushes, hisses and low-passes the render.
Order matters: filtering LAST is what makes the result measurably darker
(spectral centroid 514 Hz against 2207 Hz clean); filtering first left it
brighter than the original. Demo `bracket`.
