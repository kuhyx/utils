# Unified design tokens (frozen values)

Concrete instantiation of `safe-design-rules`' 28 rules. One identical
palette across every repo/stack (Flutter, web, Python/Tkinter) — not just
shared rules, the same hex values everywhere, including Flutter launcher-icon
glyphs (`app-icon` skill). Anchored on the shared icon charcoal `#211D1B` so
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
