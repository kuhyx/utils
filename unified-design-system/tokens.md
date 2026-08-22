# Unified design tokens (frozen values)

Concrete instantiation of `safe-design-rules`' 28 rules. One identical
palette across every repo/stack (Flutter, web, Python/Tkinter) — not just
shared rules, the same hex values everywhere, including Flutter launcher-icon
glyphs (`app-icon` skill).

> **This table is checked, not trusted.**
> `scripts/palette_check.py` parses all four token sources — this file,
> `web_ui/src/tokens.css`, `design_system/lib/src/tokens.dart` and gatelock's
> `LockConfig` — and fails on any hex that disagrees across them, *including a
> hex edited only here*. It also fails on a colour token that no stack's map
> accounts for, so adding a token to one stack and forgetting the others is a
> CI failure rather than silent drift. Runs in `.github/workflows/palette-drift.yml`,
> deliberately with no `paths:` filter: drift is a disagreement *between*
> packages, so a path-scoped trigger would skip exactly the edit that causes it.
> Editing any value below means editing it in all four places. Anchored on the shared icon charcoal `#211D1B` so
the UI palette and the icon family cohere instead of adding a second
"near-black." Warm-tinted throughout (rule 10) — superseded from an earlier
cool-tinted draft; every neutral is a byte-reversed (RRGGBB→BBGGRR) mirror of
that draft's value, so relative lightness/contrast steps are unchanged, only
the tint shifts from blue toward red/brown.

## Neutrals

| Token             | Hex       | Notes                                            |
| ------------------ | --------- | ------------------------------------------------- |
| `ink`               | `#211D1B` | Dark bg. Same value as the icon charcoal.         |
| `ink-raised-1`      | `#2B2624` | Dark elevated surface, step 1.                    |
| `ink-raised-2`      | `#38312E` | Dark elevated surface, step 2 (≤12% luma vs bg).  |
| `line-dark`         | `#463E3A` | Border on dark surfaces.                          |
| `text-on-dark`      | `#ECEAE9` | Primary text on dark. Near-white, not pure.       |
| `muted-on-dark`     | `#AAA09A` | Secondary/caption text on dark.                   |
| `paper`             | `#F6F4F3` | Light bg.                                         |
| `paper-raised`      | `#FCFBFB` | Light elevated surface — lighter than bg (rule 15). |
| `line-light`        | `#E0DAD7` | Border on light surfaces (≥3:1 vs bg and card).   |
| `text-on-light`     | `#211D1B` | Reuses `ink` — deliberate symmetry.               |
| `muted-on-light`    | `#70625B` | Secondary/caption text on light.                  |

## Accent + semantic roles

One set, used identically everywhere — UI, icons, everything. All four now
cluster in the red-orange-yellow-olive wedge, distinguished mainly by
lightness (danger 130 < accent 143 < success ~150 < warning 171 — a flagged,
deliberate tradeoff, not an oversight): a colorblind/at-a-glance
distinguishing risk the user accepted over keeping green/red as a semantic
exception.

| Token     | Hex       |
| --------- | --------- |
| `accent`  | `#B8862E` |
| `info`    | `#B8862E` (= accent) |
| `success` | `#8A9A3C` |
| `warning` | `#E0A63C` |
| `danger`  | `#E2585F` |
| `on-fill` | `#211D1B` (= `ink`) |

`on-fill`: text/icon color for anything drawn **on top of** a filled
accent/success/warning/danger surface (a primary button, a filled badge) —
never `text-on-dark`. All four fill colors sit in the same mid-light
lightness band (that's the accent/success/warning/danger clustering noted
above), so near-white text under-contrasts on every one of them (measured
2.2:1–3.6:1 against WCAG's 4.5:1 body-text floor); `ink` text passes on all
four (5.8:1–9.7:1). This is a closed rule, not a per-color judgment call —
never pick text color per fill, always `on-fill`.

Do not confuse `on-fill` with text on a **scrim/overlay** (a dark
semi-transparent backdrop behind a modal or a translucent control chip over
an image) — those stay `text-on-dark` (near-white), fixed regardless of
page theme, since the scrim itself is always dark. `on-fill` only applies to
the four *opaque* semantic fills above.

## Categorical ramp

For **charts, tags and category dots** — anything that needs N mutually
distinguishable colours with no inherent meaning. Never for semantic state:
success/warning/danger still own that, and mixing the two vocabularies is what
makes a "red" category read as an error.

| Token   | Hex       | L\* |
| ------- | --------- | --- |
| `cat-1` | `#C57293` | 58  |
| `cat-2` | `#398FC0` | 56  |
| `cat-3` | `#C85A32` | 52  |
| `cat-4` | `#228736` | 49  |
| `cat-5` | `#8D58BB` | 47  |
| `cat-6` | `#686D2C` | 44  |

**This ramp deliberately leaves the warm wedge**, and it is the only token group
that does. Accent/success/warning/danger cluster in red-orange-yellow-olive and
are separated mainly by lightness — a tradeoff that works when meaning carries
the signal. A categorical ramp has no meaning to lean on, so hue separation *is*
the requirement. Treating this as drift and "correcting" it back toward the
wedge would destroy the only property it has.

Chosen by search under four hard constraints, not by eye: pairwise CIE ΔE ≥ 20
under normal vision *and* simulated deuteranopia/protanopia/tritanopia, ≥ 3:1
against **both** backgrounds, monotonically decreasing lightness, and muted
saturation.

**Do not copy the measured margins into this file.** Run the check — it prints
every one of them and fails if any regresses:

```
python3 unified-design-system/scripts/ramp_check.py
```

Two consequences worth keeping in prose, because the numbers alone do not say
them. The both-backgrounds rule is the binding constraint: colours legible on
a near-black *and* a near-white field only exist around L\* 44–59, which is why
the ramp is mid-toned rather than spanning light to dark. And because lightness
falls monotonically, hue and lightness encode redundantly, so `cat-1…6` still
reads as an ordinal scale in greyscale or under severe CVD.

Use them **in order** for ordered data, and *by position* for unordered data —
never pick "the green one" because green means good, which is the semantic
vocabulary leaking back in. Need a seventh category? That is a signal to group
the tail into "other", not to extend the ramp: a 7th hue cannot clear ΔE 20
against all six under CVD within the L\* 44–59 band.

## Spacing scale (4px base)

`xs 4 · sm 8 · md 16 · lg 24 · xl 32 · xxl 48`

Every spacing/sizing value in a file should land on this scale. Round
outliers to the nearest step rather than introducing a new one.

## Corner radius scale

`sm 8` (buttons, inputs, chips) · `md 12` (cards) · `lg 16` (sheets, dialogs).

Nesting (rule 24): an inner element's radius = outer radius − the gap between
inner and outer edges, computed per instance — not a fixed constant. E.g. an
`lg` (16px) container with 4px of padding before its child starts should give
that child a 12px radius, not reuse 16 or invent an unrelated value.

## Typography scale

| Role       | Size (px) | Tracking                          |
| ---------- | --------- | ---------------------------------- |
| `display`  | 32        | tight (e.g. −0.2px)                |
| `title`    | 24        | tight (e.g. −0.1px)                |
| `subtitle` | 20        | default                            |
| `body`     | 16        | default — the floor (rule 20)      |
| `label`    | 14        | loose (+0.05–0.1em), chrome only   |
| `caption`  | 12        | loose (+0.1–0.2em), chrome only    |

`body` (16px) is the minimum for anything a user actually reads.
`label`/`caption` are for UI chrome (timestamps, badges, tags) — never for
primary reading content.

Two typefaces max (rule 23): one system sans stack for all UI text
(`-apple-system, "Segoe UI", Roboto, system-ui, sans-serif` on web; platform
default on Flutter/Tk), one monospace stack reserved for code/data-dense
contexts only.

Line length (rule 21): prose/paragraph blocks capped at `max-width: 40rem`
(~640px, ~65–70 characters).

### The sizes above are **pixels**. On Tk that means a negative number.

Tk encodes the unit in the *sign* of the font size: **positive = points,
negative = pixels**. So `("Arial", 16)` is 16 **points**, not 16 pixels, and
renders ~37% larger than this scale specifies. Measured:

| Spec | `size=16` (points) | `size=-16` (pixels) |
| ---- | ------------------ | ------------------- |
| `linespace` | 26px | 19px |
| `ascent`    | 21px | 15px |

Always write the negative form in Tk — `font=(family, -16)` for `body`. Passing
the positive px value straight through inflates every string in the app by a
third, which is enough on its own to push a 768px-tall layout off-screen (it
did: it was the root cause of the diet-guard meal gate needing 974px in a 724px
pane). This is a silent failure — nothing errors, the text is just wrong-sized —
so it is checked by the gate rather than left to review.

Flutter `fontSize` and CSS `px` are already pixels; no sign convention there.

## Buttons

Horizontal padding = 2× vertical (rule 22). Canonical: vertical `12px`,
horizontal `24px` (both on the spacing scale: 12 = 3×4, 24 = 6×4).

## Shadow policy (rules 16, 26, 27)

Pick exactly one depth technique per surface — never a shadow and a lighter
fill on the same element, never a border-only style next to a shadowed one
at the same z-level.

- **Dark surfaces: no shadows, ever.** Elevation is `ink-raised-1`/`-2` fill
  steps only.
- **Light surfaces**: shadows allowed *only* on floating/overlay elements
  (dropdown menus, modal dialogs) — never on inline cards or list rows.
  Two tiers, blur = 2× offset, tinted from `ink` (never pure black):
  - Level 1 (e.g. a dropdown): `0 2px 4px rgba(33, 29, 27, 0.12)`
  - Level 2 (e.g. a modal): `0 4px 8px rgba(33, 29, 27, 0.16)`

## Icon-next-to-text contrast (rule 28)

Icons adjacent to text render at ~72% opacity of the text's color, or use the
`muted` role instead of the full-strength text role — never equal contrast.

## Focus ring

| Token        | Value      | Notes                                        |
| ------------ | ---------- | -------------------------------------------- |
| `focus-ring` | `#B8862E` (= `accent`) | 2px, offset 1px. |

Why the platform default is not good enough, and the Tk
`highlightcolor`/`highlightbackground` trap, are in
[`operability.md`](operability.md#the-focus-ring-token).

## Operability and screen size

Keyboard-only reachability and the small-screen budget are requirements, not
suggestions: several of these apps are lockers that hold a global input grab,
so a control only a pointer can reach is a bricked machine. Both, plus the
`focus-ring` token, are in [`operability.md`](operability.md).
