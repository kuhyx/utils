"""Keeping several Text widgets showing the same string.

Split from :mod:`gatelock._surfaces` for the 250-line cap. A lock renders one
surface per output, so a multi-line field exists once per monitor and all the
copies have to agree; ``tk.StringVar`` does this for Entry and Spinbox but not
for ``tk.Text``, which has no textvariable.

Re-exported from :mod:`gatelock._surfaces` and from :mod:`gatelock`, so
existing imports of either name keep working.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# Tk text indices: the first character, and the last one before the newline
# Text always appends.
_TEXT_START = "1.0"
_TEXT_END = "end-1c"


class TextMirror:
    """Keeps N ``tk.Text`` widgets showing the same value.

    ``tk.Text`` has no ``textvariable``, so it is the one widget that cannot
    ride the shared-``StringVar`` mechanism the rest of the mirroring uses.
    """

    def __init__(self, widgets: Sequence[tk.Text], var: tk.StringVar) -> None:
        """Bind ``widgets`` to each other through ``var``."""
        self._widgets = list(widgets)
        self._var = var
        self._syncing = False
        for widget in self._widgets:
            widget.bind("<KeyRelease>", self._on_key_release, add="+")
        self._var.trace_add("write", self._on_var_write)

    def _on_key_release(self, event: tk.Event[tk.Text]) -> None:
        """Push the edited widget's content into the shared variable."""
        if self._syncing:
            return
        self._syncing = True
        try:
            self._var.set(event.widget.get(_TEXT_START, _TEXT_END))
        finally:
            self._syncing = False
        self._fan_out(source=event.widget)

    def _on_var_write(self, *_args: str) -> None:
        """Push the shared variable's value into every widget."""
        if self._syncing:
            return
        self._fan_out(source=None)

    def _fan_out(self, *, source: tk.Text | None) -> None:
        """Write the variable's value into every widget but ``source``."""
        value = self._var.get()
        self._syncing = True
        try:
            for widget in self._widgets:
                if widget is source or widget.get(_TEXT_START, _TEXT_END) == value:
                    continue
                widget.delete(_TEXT_START, "end")
                widget.insert(_TEXT_START, value)
        finally:
            self._syncing = False


def mirror_text_widgets(widgets: Sequence[tk.Text], var: tk.StringVar) -> TextMirror:
    """Keep several ``tk.Text`` mirrors in sync through one variable."""
    return TextMirror(widgets, var)
