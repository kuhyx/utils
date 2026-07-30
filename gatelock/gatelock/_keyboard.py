r"""Keyboard-operability helpers for lock surfaces.

Every function here works around a **Tk default**, not an application mistake.
That is why they belong in the shared backend: the same three defects otherwise
recur in every locker, and each one is a lockout rather than an annoyance,
because a lock surface holds a global input grab with VT switching disabled.
There is no other window to click and no console to escape to.

The defaults, verified against Tk 8.6's own class bindings:

- ``tk.Text`` traps Tab. ``bind Text <Key-Tab>`` runs
  ``tk::TextInsert %W \\t; focus %W; break``, so Tab inserts a literal tab and
  refocuses the widget, and ``<Shift-Tab>`` is bound to do nothing. The only
  built-in exits are ``Ctrl+Tab``/``Ctrl+Shift+Tab``, which no UI advertises.
- ``tk.Button`` ignores Enter. On X11 ``bind Button <space>`` exists but there
  is **no** ``<Return>`` binding, and ``entry.tcl``/``spinbox.tcl`` bind
  ``<Return>`` to ``{# nothing}``. So Space works and Enter -- the key a user
  reaches for to submit -- does nothing at all.
- Focus is invisible. Tk ships ``highlightcolor="#000000"`` at
  ``highlightthickness=1``, i.e. a black ring on the palette's near-black
  background. See :meth:`gatelock.LockConfig.focus_kwargs`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk


def escape_text_tab_trap(text: tk.Text) -> None:
    """Make Tab / Shift-Tab move focus out of a ``tk.Text``.

    Without this a keyboard-only user who tabs into a multi-line field cannot
    get back out to the submit button, which on a lock surface means they
    cannot satisfy the lock at all.

    Returning ``"break"`` is what stops Tk's own class binding from also
    running and inserting the tab character.

    Args:
        text: The widget to un-trap.
    """

    def _forward(_event: tk.Event) -> str:
        text.tk_focusNext().focus_set()
        return "break"

    def _backward(_event: tk.Event) -> str:
        text.tk_focusPrev().focus_set()
        return "break"

    text.bind("<Tab>", _forward, add="+")
    text.bind("<Shift-Tab>", _backward, add="+")
    # X11 delivers Shift+Tab as its own keysym, which <Shift-Tab> alone misses.
    text.bind("<ISO_Left_Tab>", _backward, add="+")


def bind_activate(widget: tk.Widget) -> None:
    """Make Enter activate a button-like widget, as well as Space.

    Tk binds only ``<space>`` on X11, so every button in an unmodified lock UI
    is Space-only. Both the main Return key and the keypad's Enter are bound,
    since they are distinct keysyms.

    Args:
        widget: A widget exposing ``invoke()`` (Button, Checkbutton, ...).
    """

    def _activate(_event: tk.Event) -> str:
        widget.invoke()
        return "break"

    widget.bind("<Return>", _activate, add="+")
    widget.bind("<KP_Enter>", _activate, add="+")


def bind_cancel(widget: tk.Misc, callback: object) -> None:
    """Bind Escape on a widget's toplevel to a cancel/back action.

    Bound at the toplevel rather than the widget so Escape works wherever focus
    currently sits, which is the point -- a user who has tabbed somewhere
    unexpected still needs the way back.

    This is for *cancel* affordances only. Some lockers deliberately refuse
    dismissal (an alarm you must solve a challenge to silence); making their
    sanctioned back/cancel button reachable does not weaken that, but do not
    use this to add an exit a lock is designed not to have.

    Args:
        widget: Any widget in the target toplevel.
        callback: Zero-argument callable invoked on Escape.
    """
    if not callable(callback):
        message = "callback must be callable"
        raise TypeError(message)

    def _cancel(_event: tk.Event) -> str:
        callback()
        return "break"

    widget.winfo_toplevel().bind("<Escape>", _cancel, add="+")
