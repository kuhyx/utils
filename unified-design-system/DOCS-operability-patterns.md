# Pointer-free + small-screen: per-stack patterns

Split out of [`README.md`](README.md), which covers the palette and the
per-stack *theming* pattern. This file is the other half: how to satisfy the
operability requirements in [`operability.md`](operability.md) in Flutter, on
the web, and in Python/Tkinter.

The rules themselves are in [`tokens.md`](tokens.md) (*Pointer-free
operability*, *Screen size*). This is how to implement them per stack. Both are
machine-checked — a static lint in pre-commit plus a render test in each repo's
suite — so treat these as the shape the checks expect.

### Flutter

```dart
// Reach: never a bare GestureDetector for an action.
InkWell(onTap: select, child: cell)                    // focusable + Enter/Space
// A destructive action needs a focusable control, not just onLongPress:
IconButton(icon: Icon(Icons.delete), onPressed: confirmDelete)

// App-level accelerators. On the Chrome --app desktop surface, avoid chords
// Chrome reserves (Ctrl+N/T/W/Shift+N) — they never reach Flutter.
Shortcuts(shortcuts: {
  SingleActivator(LogicalKeyboardKey.keyS, control: true): SaveIntent(),
  SingleActivator(LogicalKeyboardKey.escape): DismissIntent(),
}, child: Actions(actions: {...}, child: child));

// Size: budget height, clamp width.
final short = MediaQuery.sizeOf(context).height < 700;   // 768 minus chrome
ConstrainedBox(constraints: BoxConstraints(maxWidth: kProseMaxWidth), child: prose);
```

Any screen whose content can grow needs a `SingleChildScrollView`/`ListView` —
a `Column` with one `Expanded` child does not scroll, it just collapses the
flexible child until it is unusable. Bottom sheets need `isScrollControlled:
true` plus an inner scroll view.

Note on **Flutter web** (todo-app and diet-guard's desktop surface are the web
build in a Chrome `--app` window, not the Linux embedder): the semantics tree is
not built unless assistive tech is detected, so `Semantics` is not a substitute
for real focusability — use focusable widgets, and treat `Semantics` as
additive.

### Web

`:focus-visible` must be styled everywhere, and never removed:

```css
:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
/* Never `outline: none` without an equally visible replacement. */
```

Verify at the required viewports with no horizontal scroll and no *inner*
scrollbar: `1366x768` and `1024x600` at minimum. Prefer a compact baseline that
grows, over a desktop layout that must shrink.

### Python/Tkinter

Font sizes are **negative** (see `tokens.md` — positive means points and
inflates everything ~37%). The focus ring and both scales live on
`gatelock.LockConfig` so all four lockers inherit them:

```python
# focused ring — NOT highlightbackground, which is the *unfocused* ring
widget.configure(highlightcolor=cfg.focus_ring, highlightthickness=2)
widget.configure(font=(cfg.font_family, -cfg.type_body))   # negative == pixels
```

Tk specifics that are easy to get wrong, all verified against Tk 8.6's own
class bindings:

- `tk.Button` binds `<space>` on X11 but **not** `<Return>`; `Entry`/`Spinbox`
  bind `<Return>` to nothing. Bind `<Return>` yourself for submit.
- `tk.Text` traps `<Tab>` (inserts a literal tab, refocuses itself) and makes
  `<Shift-Tab>` a no-op. Rebind both to move focus, or the box is a dead end.
- `tk.Canvas` has no class key bindings, so a Canvas scroll viewport is not even
  a focus stop. Bind `<Prior>`/`<Next>`/arrows, **and** add a `<FocusIn>` handler
  on children that scrolls the focused child into view — clipping does not
  unmap children, so focus walks into invisible fields by default.
- `OptionMenu`/`Menubutton` default to `takefocus=0`. On lock surfaces they are
  banned anyway (a posted menu steals the grab); use radio buttons.
- `ttk.Notebook` needs an explicit `enable_traversal()` for `Ctrl+Tab` /
  `Ctrl+PageDown` / `Alt`+mnemonic.
- Verify the focus ring by *walking* it (`tk_focusNext`), not by reading code.

Measure the height rather than eyeballing it — this is how the meal-gate
overflow was found, and it is what the render half of the gate does:

```bash
xvfb-run -s "-screen 0 1366x768x24" python3 -m your_pkg.tests.measure_layout
# assert frame.winfo_reqheight() <= available_pane_height
```

Measure both empty **and** fully populated (a day of meals logged, history rows
present) — the empty case is not the worst case.
