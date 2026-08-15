# Screen size (required)

Split out of `tokens.md` on 2026-08-15 to hold every file under the shared
250-line cap, when the categorical ramp was added. Both are part of the same
token spec — this is a filing change, not a scoping change.

| Target | Requirement |
| ------ | ----------- |
| **1366x768** | Fully usable. Nothing clipped, nothing unreachable. This is the primary machine. |
| **1024x600** | Degrades gracefully — scrolls rather than clips. No hard minimum size above this. |

Rules:

1. **Budget the height, don't assume it.** 768px is the design target, not 1080.
   Mixing a proportional content area with fixed chrome (`height = 0.7·H` above a
   fixed-height button row) silently works at 1080 and fails at 768 — compute the
   content budget as `available − measured chrome`.
2. **Any view that can grow must scroll.** Lists, forms, anything whose height
   depends on data (a day's log, an error string, accumulated history). An
   unbounded error message is a real overflow source.
3. **Never centre unscrollable content that can overflow.** A centre-anchored
   container clips **symmetrically** when it is too tall — losing the header *and*
   the submit button, with no scrollbar and no indication anything is missing.
   Top-anchor it inside a scroll container instead.
4. **Clamp width as well.** Prose stays at the 40rem/640px cap (rule 21) and
   single-purpose inputs get a sensible max — a 4-digit number field stretched to
   1334px is a violation even though nothing is clipped.
5. **Don't let text scale break layout.** Rows that must not overflow use `Wrap`/
   `Flexible` rather than a bare `Row`.

`1366x768` and `1024x600` are landscape and *short*. Phone-portrait test sizes do
not exercise either constraint, so both belong in the test matrix explicitly.
