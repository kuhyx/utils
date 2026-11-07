# Copyright (c) 2026 Krzysztof Rudnicki
"""A small always-on-top strip in the top-right corner of the primary output.

For the time a gate is *stood down but not done*: the lock is not up, yet the
user still owes something (a morning session to finish, solves to submit).
Without it the screen just clears and the lock returns out of nowhere.

Top-right because the centre is where the user's actual work sits and the
bottom-right is where desktop notifications land. Lifted from leetcode-guard's
study strip so every gate shows the same thing in the same place.

The strip never grabs input and never re-asserts a grab; its tick only
refreshes the text and re-lifts the window. ``supply`` returning ``None`` is
the one way it ends on its own, so the owner decides when the debt is gone.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import tkinter as tk
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from gatelock._config import LockConfig
    from gatelock._output_types import OutputRect, OutputScan

_logger: Final = logging.getLogger(__name__)

_TOPMOST_ON: Final = 1
CORNER_STRIP_WIDTH_PX: Final = 420
CORNER_STRIP_TICK_MS: Final = 1_000


@dataclass(frozen=True)
class StripContent:
    """What the strip says: one bold title and a few plain lines."""

    title: str
    lines: tuple[str, ...]


def corner_rect(scan: OutputScan) -> OutputRect | None:
    """The rectangle to sit on: the primary live output, else the first live.

    The whole X screen spans every monitor on a multi-head desk and would park
    the strip on the far one, so it is always one output's rectangle.
    """
    live = scan.live
    for output in live:
        if output.primary:
            return output.rect
    return live[0].rect if live else None


def corner_geometry(rect: OutputRect, *, width: int, height: int, inset: int) -> str:
    """Tk geometry for a ``width`` x ``height`` window in ``rect``'s top-right."""
    x = rect.x + rect.width - width - inset
    y = rect.y + inset
    return f"{width}x{height}+{x}+{y}"


class CornerStrip:
    """Handle on a built strip: refresh it, tick it, tear it down."""

    def __init__(
        self,
        window: tk.Toplevel,
        title_label: tk.Label,
        line_labels: Sequence[tk.Label],
        *,
        tick_ms: int = CORNER_STRIP_TICK_MS,
    ) -> None:
        """Wrap an already-built strip window."""
        self.window = window
        self._title = title_label
        self._lines = tuple(line_labels)
        self._tick_ms = tick_ms
        self._job: str | None = None
        self._destroyed = False

    @property
    def closed(self) -> bool:
        """Whether the strip is gone (destroyed, or broke on a refresh)."""
        return self._destroyed

    def show(self, content: StripContent) -> None:
        """Write ``content`` and re-lift; lines past the content are blanked."""
        if self._destroyed:
            return
        try:
            self._title.configure(text=content.title)
            for index, label in enumerate(self._lines):
                text = content.lines[index] if index < len(content.lines) else ""
                label.configure(text=text)
            self.window.lift()
        except tk.TclError:
            # A fullscreen window over us is cosmetic; an exception escaping a
            # Tk callback is not. Stop ticking and say so.
            _logger.warning("the corner strip could not refresh", exc_info=True)
            self._destroyed = True

    def schedule(
        self,
        supply: Callable[[], StripContent | None],
        *,
        on_close: Callable[[], None],
    ) -> None:
        """Tick: show ``supply()`` until it returns None, then close."""
        if self._destroyed:
            return

        def run() -> None:
            content = supply()
            if content is None:
                self.destroy()
                on_close()
                return
            self.show(content)
            if not self._destroyed:
                self._job = self.window.after(self._tick_ms, run)

        self._job = self.window.after(self._tick_ms, run)

    def destroy(self) -> None:
        """Cancel the tick and tear the window down. Idempotent."""
        if self._destroyed:
            return
        self._destroyed = True
        try:
            if self._job is not None:
                self.window.after_cancel(self._job)
            self.window.destroy()
        except tk.TclError:
            _logger.warning("the corner strip could not be destroyed", exc_info=True)


def build_corner_strip(
    root: tk.Misc,
    config: LockConfig,
    content: StripContent,
    *,
    rect: OutputRect,
    max_lines: int = 3,
) -> CornerStrip:
    """Create the strip in ``rect``'s top-right corner, showing ``content``.

    ``max_lines`` labels are built up front so later content can grow into
    them without re-layout; the height is whatever those labels ask for.
    """
    width = CORNER_STRIP_WIDTH_PX
    window = tk.Toplevel(root)
    # Override-redirect must be set while withdrawn or the geometry is ignored.
    window.withdraw()
    window.overrideredirect(boolean=True)
    window.configure(bg=config.palette.field_bg)
    wrap = width - 2 * config.space("md")

    title = tk.Label(
        window,
        text=content.title,
        font=config.font("label", bold=True),
        fg=config.palette.fg,
        bg=config.palette.field_bg,
        wraplength=wrap,
    )
    title.pack(pady=(config.space("sm"), 0), padx=config.space("md"))
    lines = []
    for index in range(max_lines):
        label = tk.Label(
            window,
            text=content.lines[index] if index < len(content.lines) else "",
            font=config.font("body" if index == 0 else "caption"),
            fg=config.palette.accent if index == 0 else config.palette.muted,
            bg=config.palette.field_bg,
            wraplength=wrap,
            justify="left",
        )
        label.pack(padx=config.space("md"))
        lines.append(label)
    if lines:
        lines[-1].pack_configure(pady=(0, config.space("sm")))

    window.update_idletasks()
    height = int(window.winfo_reqheight())
    window.geometry(
        corner_geometry(rect, width=width, height=height, inset=config.space("md"))
    )
    window.deiconify()
    window.lift()
    # A hint most window managers honour even for override-redirect windows.
    window.attributes("-topmost", _TOPMOST_ON)
    return CornerStrip(window, title, lines)
