"""One logical widget, fanned out across every output's surface.

A gate covers every monitor the user can see, so each surface needs its own
copy of the same logical widget: one countdown label becomes three real
labels. Every consuming app grew its own version of this (~916 lines across
four repos) and each arrived at a slightly different set of guarantees.
This is the union of what they all actually needed, with the sharp edges
that only some of them had fixed.

Four behaviours are load-bearing, each of them a bug in at least one donor:

1. **A dead copy must not raise.** Surfaces are destroyed and rebuilt when
   outputs change, and a fan-out that touches a destroyed widget raises
   ``TclError`` in the middle of a repaint -- leaving the remaining copies
   untouched. Every operation here suppresses it per copy and carries on, so
   one dead monitor cannot stop the others updating.
2. **Zero outputs is a real state, not an error.** A group can legitimately
   hold nothing (no connected output yet, or every surface torn down), so
   :attr:`first` returns ``None`` rather than raising ``IndexError``.
3. **Focus is singular.** ``focus_set``/``focus_force`` deliberately do *not*
   fan out: focusing every copy would hand X input focus to whichever surface
   happened to be last. They move focus to the first copy that accepts it.
4. **Copies of a text field diverge on purpose.** Entries share a
   ``StringVar`` and converge, but a group makes no attempt to mirror
   ``tk.Text`` or ``tk.Listbox`` content -- the user answers on whichever
   monitor they are looking at, and :meth:`WidgetGroup.first_where` is how a
   caller reads back the copy that was actually used.

Storage is a single list of ``(output_name, widget)`` pairs rather than two
parallel lists. The parallel form let a group be built with widgets but no
output names, so :meth:`discard` -- which zips them strictly -- would raise
``ValueError`` on any group built that way. Pairing them makes that
unrepresentable.
"""

from __future__ import annotations

import contextlib
import tkinter as tk
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_W = TypeVar("_W", bound=tk.Misc)


class WidgetGroup(Generic[_W]):
    """Every per-output copy of one logical widget.

    Build one per logical widget, :meth:`add` a copy as each surface is
    built, and :meth:`discard` an output's copy when its surface is torn
    down. Operations fan out across the live copies; reads come from the
    first copy that answers.
    """

    def __init__(self, pairs: list[tuple[str, _W]] | None = None) -> None:
        """Create a group, optionally seeded with ``(output_name, widget)``."""
        self._pairs: list[tuple[str, _W]] = list(pairs) if pairs else []

    def add(self, output_name: str, widget: _W) -> None:
        """Record ``widget`` as this group's copy on ``output_name``."""
        self._pairs.append((output_name, widget))

    def discard(self, output_name: str) -> None:
        """Forget every copy belonging to ``output_name``.

        Does not destroy the widgets: the surface teardown that prompted this
        already destroys its own widget tree, and destroying a second time is
        what turns a routine output change into a ``TclError`` storm.
        """
        self._pairs = [pair for pair in self._pairs if pair[0] != output_name]

    def clear(self) -> None:
        """Forget every copy, without destroying anything."""
        self._pairs = []

    def __iter__(self) -> Iterator[_W]:
        """Iterate the live copies, in the order they were added."""
        return (widget for _name, widget in self._pairs)

    def __len__(self) -> int:
        """Return how many copies this group holds."""
        return len(self._pairs)

    @property
    def outputs(self) -> tuple[str, ...]:
        """Return the output names this group has a copy on."""
        return tuple(name for name, _widget in self._pairs)

    @property
    def first(self) -> _W | None:
        """Return the first copy, or ``None`` when the group is empty.

        ``None`` rather than an ``IndexError``: a gate with no connected
        output is a state the apps reach, not a programming mistake.
        """
        return self._pairs[0][1] if self._pairs else None

    def first_where(self, predicate: Callable[[_W], bool]) -> _W | None:
        """Return the first copy satisfying ``predicate``, else ``None``.

        This is how a caller reads back a deliberately-diverged widget --
        typically "the first copy whose text is not blank", i.e. the monitor
        the user actually typed on. A copy that raises ``TclError`` while
        being examined is treated as not matching, so a destroyed surface
        cannot break the read.
        """

        def matches(widget: _W) -> bool:
            try:
                return predicate(widget)
            except tk.TclError:
                return False

        return next((widget for widget in self if matches(widget)), None)

    def _each(self, action: Callable[[_W], object]) -> None:
        """Apply ``action`` to every copy, skipping ones that have died."""
        for widget in self:
            with contextlib.suppress(tk.TclError):
                action(widget)

    def configure(self, **kwargs: object) -> None:
        """Configure every copy.

        ``kwargs`` is typed ``object`` rather than ``str`` so a group can
        carry ``command=<callable>``; two donors typed it ``str`` and had to
        reach past the group to wire a button up.
        """
        self._each(lambda widget: widget.configure(**kwargs))

    # Tk spells it both ways, and the donors were split; keep both so a
    # migrated call site does not have to change spelling.
    config = configure

    def bind(
        self, sequence: str, func: Callable[[tk.Event], object], *, add: bool = True
    ) -> None:
        """Bind ``sequence`` on every copy.

        ``add`` defaults to True: a group is rebound on repaint, and
        replacing bindings by default silently drops handlers another part of
        the app installed on the same widget.
        """
        self._each(lambda widget: widget.bind(sequence, func, add="+" if add else ""))

    def pack(self, **kwargs: object) -> None:
        """Pack every copy with the same options."""
        self._each(lambda widget: widget.pack(**kwargs))

    def pack_forget(self) -> None:
        """Un-pack every copy, leaving the widgets alive."""
        self._each(lambda widget: widget.pack_forget())

    def destroy(self) -> None:
        """Destroy every copy and empty the group."""
        self._each(lambda widget: widget.destroy())
        self.clear()

    def focus_set(self) -> None:
        """Focus the first copy that accepts it.

        Deliberately not a fan-out: X input focus is singular, so focusing
        every copy just means the last surface wins, unpredictably.
        """
        self._focus_one(lambda widget: widget.focus_set())

    def focus_force(self) -> None:
        """Force focus onto the first copy that accepts it."""
        self._focus_one(lambda widget: widget.focus_force())

    def _focus_one(self, action: Callable[[_W], object]) -> None:
        """Apply ``action`` to the first copy that does not raise."""

        def accepted(widget: _W) -> bool:
            try:
                action(widget)
            except tk.TclError:
                return False
            return True

        next((widget for widget in self if accepted(widget)), None)
