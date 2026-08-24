# The scrollable lock viewport

Design rationale for `gatelock/_scrollable.py` and its collaborators
(`_scrollfit.py`, `_scrollkeys.py`, `_userintent.py`). Kept here rather
than in the module docstring so the module itself stays readable in one
piece; the behaviour it describes is load-bearing, not historical.

A keyboard-scrollable, focus-following viewport for lock-surface content.

Lock surfaces cannot solve "content taller than the screen" the obvious way.
A scrollable dialog would be a second ``Toplevel``, and on an
override-redirect lock surface a second toplevel steals the Tk grab, which the
recovery tick then kills a second later -- the 2026-07-26 failure where a
frozen sport selector logged a walk as table tennis. So the viewport has to
live inside the surface's own widget tree, which is what this provides.

Three defects this exists to prevent, all of them Tk defaults rather than
oversights in any one app:

1. **Centered content clips symmetrically.** A ``place``-centered frame takes
   its *requested* size, so when it is too tall the parent shears equal
   amounts off the top *and* the bottom -- losing the header and the submit
   button together, with no scrollbar and no hint anything is missing. This
   top-anchors content inside a scroll region instead.
2. **A Canvas viewport is not keyboard-scrollable.** ``tk.Canvas`` has no
   class-level key bindings at all, so ``::tk::FocusOK`` rejects it as a focus
   stop and the only way to move the view is dragging the scrollbar thumb with
   a pointer. This makes the canvas focusable and binds PageUp/PageDown,
   Home/End and arrows.
3. **Focus walks into invisible widgets.** Canvas clipping does not *unmap* a
   child, so every scrolled-out-of-view field stays ``winfo viewable`` and
   stays in the tab chain, while Tk never scrolls to follow focus. Tabbing
   therefore lands on fields the user cannot see and cannot bring into view.
   :meth:`ScrollableSurface.scroll_into_view` fixes that, but only for focus
   the *user* moved.

Wheel scrolling is bound too, but as an addition -- never as the only path.

**Scrolling is the fallback, not the design.** A lock screen is supposed to
fit its screen; content that overflows is a layout defect, and :meth:`finalize`
logs it at ``warning`` so it gets fixed rather than lived with. While the
content fits -- the normal case -- the scroll region is pinned to the viewport
and the scrollbar is hidden, so the view cannot move at all. When it does
overflow, the view still only moves in response to a keypress, a click or the
wheel: an earlier version followed *programmatic* focus too, and since the apps
re-focus a widget on every repaint, the screen scrolled itself to mid-content
and back while the user was doing nothing (reported 2026-08-03, 1366x768).
