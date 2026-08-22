# Pointer-free operability and screen size (required)

Split out of [`tokens.md`](tokens.md), which freezes the palette and the
scales. These are the *behavioural* requirements that use those tokens — a
token file should be readable as a table of values, and these are rules with
reasons attached.

Per-stack implementations of everything here are in
[`operability-patterns.md`](operability-patterns.md).

## Pointer-free operability (required)

**Every action must be reachable and activatable with the keyboard alone.** No
mouse, no touchpad, no touch. This is not an accessibility nicety here: several
of these apps are *lockers* that hold a global input grab with VT switching
disabled, so a control only a pointer can reach is not an inconvenience — it is
a bricked machine.

Six things must hold on every surface:

1. **No pointer-only handler.** Any `onTap`/`onLongPress`/`<Button-1>`/click
   handler needs a keyboard-reachable equivalent on the same action. A bare
   `GestureDetector` and an `onLongPress`-only destructive action are both
   defects. Long-press in particular has *no* keyboard analogue — never make it
   the only path to an action.
2. **Everything interactive is a focus stop.** Widgets that opt out of the focus
   ring (`takefocus=0`, which Tk's `Menubutton`/`OptionMenu` default to) are
   unreachable. Verify by walking the real ring, not by reading the code.
3. **Focus is visible.** See the focus-ring token below — the platform default
   is a black ring, which vanishes on `ink`.
4. **Focus never lands somewhere invisible.** If a container scrolls, focus
   entering a clipped child must scroll it into view. Clipping does not remove a
   widget from the focus ring, so this is the default failure, not an edge case.
5. **Scrolling is keyboard-driven.** A scroll container needs `PageUp`/`PageDown`
   and arrow keys, not just a draggable thumb and a wheel.
6. **Confirm/submit and cancel/back have accelerators.** `Enter` submits, `Escape`
   cancels. On Tk, note `Enter` does **not** activate a `tk.Button` on X11 (only
   `Space` does) and is bound to nothing on `Entry`/`Spinbox` — you must bind it.

### The focus-ring token

`focus-ring` is `#B8862E` (= `accent`), 2px at 1px offset. It is defined in
[`tokens.md`](tokens.md#focus-ring) with the rest of the palette, because
`scripts/palette_check.py` parses that file — a token it cannot see is a token
nothing compares across the four stacks.

Platform defaults are wrong on this palette: Tk ships
`highlightcolor="#000000"` with `highlightthickness=1`, i.e. a black ring on
`ink` (`#211D1B`) — invisible. Set `focus-ring` explicitly. Never
`highlightthickness=0` on something focusable.

⚠️ On Tk, `highlightbackground` is the **unfocused** ring and `highlightcolor`
is the **focused** one. Setting only `highlightbackground` inverts the
affordance — the widget outlines when it is *not* focused and goes black when
it *is*. Set `highlightcolor`.

### Escape hatches vs. deliberate gating

Some apps intentionally resist dismissal (an alarm you must solve a challenge to
silence, a meal gate you must log a meal to clear). That gating is a feature and
this rule does not override it. What the rule requires is that the *sanctioned*
paths — solve the challenge, use the budgeted escape hatch, submit the form — are
fully keyboard-operable. Making a gate keyboard-reachable is not weakening it.

## Screen size (required)

Moved to `screen-size.md` (250-line cap): the 1366x768 / 1024x600 targets, the
height-budgeting rules, and why centring unscrollable content clips
symmetrically. Still part of this spec — read it for any layout work.
