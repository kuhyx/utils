Implement Phase 2 of the shared component work: extend `~/utils/gatelock` (Python/Tk) with the composite widgets that four guard apps each reimplemented. Treat this as `override` on the spec gate — the spec is below, it is complete, and I do not want a round of questions before you start.

**Goal.** gatelock already owns the design tokens (`LockConfig`) and the Tk plumbing, and has four consumers. Its scope stops short of composite widgets, so each consumer grew its own. Move those into gatelock and retire the copies in two proof consumers.

**This is NOT a new package.** Add to `~/utils/gatelock`, which already exists and is consumed as `gatelock @ git+https://github.com/kuhyx/utils@gatelock-v0.4.1#subdirectory=gatelock`.

**Build these four, in order:**

1. `gatelock/widgets.py` — `make_button(parent, *, text, variant, command)`. Canonical implementation is diet-guard's `_gatelock_buttons.py::make_button`: its `variant` API picks the text colour *from* the fill, which structurally prevents the `fg`-vs-`on_fill` contrast bug the README documents. leetcode-guard's `_button` (no `<Return>` binding) and screen-locker's inline `tk.Button` are the regressions being retired. Two non-obvious traps both copies had to solve independently and which the shared version must keep: `<Return>` is unbound on `tk.Button` under X11, and the default focus ring is 1px black, invisible on `#211D1B`.
2. `gatelock/widgets.py` — `heading()` and `row()`, from `leetcode_guard/_status_sections.py`.
3. **Export the existing `ScrollableSurface`** and delete `leetcode_guard/status_view.py::_scrollable`, a hand-rolled reimplementation that lost `takefocus` and the focus ring the shared version already fixes. This one is a straight accessibility regression repair, not a refactor.
4. `gatelock/widget_group.py` — `WidgetGroup`, the per-output fan-out reimplemented four times (~916 lines total: screen-locker 173, leetcode-guard 105, diet-guard 309, wake-alarm 329). Highest line-count win on this stack.

**Proof consumers: `diet-guard` and `leetcode-guard`** — the donor and the worst offender, so the API is validated against both ends. Bump **only these two**. Leave screen-locker and wake-alarm on their current pin: Phase 2 is additive, untouched consumers keep working, and restarting more live services than necessary is blast radius for no gain. Ask me before restarting anything live.

**Extraction criterion.** Build a component only where two or more repos already contain a structurally similar implementation. Shipping a widget nobody imports is the failure mode to avoid. Corollary I learned the hard way in Phase 1: when you extract something, **retire the donor copies in the same pass**, or you have shipped a duplicate rather than removed one.

**Verification gate — non-negotiable.** gatelock backs live systemd services; a bad import takes 3–4 of them down at once.

- `/usr/bin/python3 -c "import gatelock"` against the **real** interpreter, not a dev venv. The library is tag-pinned in site-packages while the apps are editable, so a cwd-relative check will lie to you.
- Then diet-guard's and leetcode-guard's test suites.
- Then launch each gate under `xvfb-run -s "-screen 0 1366x768x24"` and confirm buttons render **and `<Return>` activates them** — that is the specific regression this phase repairs, so it is the specific thing to observe.
- Do **not** touch the gate window's X-grab path. Those fullscreen surfaces carry input-hijack invariants; a deadlock there has frozen the PC before.
- `pre-commit run --files <changed>` in every touched repo, respect the 250-line file cap, and keep each repo's coverage bar.

**Done means:** the four items exist in gatelock with tests, the two proof consumers import them with their local copies deleted, `<Return>` verifiably activates a button in each gate under xvfb, and everything is committed and pushed.

Context, if you want it: `~/utils/unified-design-system/nielsen-audit.md` has the full grid and the Phase 1 record. Phase 1 (`~/utils/design_system`, Dart) is done — 7 exports, 100% coverage, six consumers — and is the pattern to imitate: `publish_to: none`, own analysis config, own tests, own coverage gate, tag-pinned git dep.
