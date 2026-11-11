# Copyright (c) 2026 Krzysztof Rudnicki
"""Finding a system credential prompt on screen and raising it, over python-xlib.

Kept apart from the policy in :mod:`gatelock._prompts` so that everything that
touches the X server lives in one place, behind :class:`XPromptProbe`. It opens
a short-lived connection per call: the caller asks at most once a second, and
only while the grab has been blocked for a while, so a persistent connection
would need a teardown path for no gain.

Candidates come from the window manager's ``_NET_CLIENT_LIST`` *and* a walk of
the root's children and grandchildren. The walk is not redundant: a bare X
server has no ``_NET_CLIENT_LIST``, and under i3 the WM_CLASS sits on the
client, one level below the frame i3 reparents it into. What gets raised is
the ancestor directly below the root (the frame), never the client.

Every X failure -- no python-xlib, no connection, a window that vanished
between listing and reading it (BadWindow) -- ends the scan with "no prompt
found", warned once per distinct message: the lock must stay on top whenever
it cannot be sure.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Protocol

from gatelock._prompt_names import PromptWindow, is_system_prompt
from gatelock._xlib import load_xlib, xlib_failures

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from types import ModuleType

    # python-xlib ships no stubs; spell out the surface used (see _randr.py).
    class _Tree(Protocol):
        children: Sequence[_XWindow]
        parent: _XWindow

    class _Attributes(Protocol):
        map_state: int

    class _Property(Protocol):
        value: Sequence[int]

    class _XWindow(Protocol):
        id: int

        def query_tree(self) -> _Tree:
            """Mirror ``Window.query_tree()``."""

        def get_wm_class(self) -> tuple[str, str] | None:
            """Mirror ``Window.get_wm_class()``."""

        def get_attributes(self) -> _Attributes:
            """Mirror ``Window.get_attributes()``."""

        def get_full_property(self, atom: object, kind: int) -> _Property | None:
            """Mirror ``Window.get_full_property()``."""

        def configure(
            self, *, stack_mode: int, onerror: Callable[[object], None]
        ) -> None:
            """Mirror ``Window.configure()``."""

    class _XScreen(Protocol):
        root: _XWindow

    class _XDisplay(Protocol):
        def screen(self) -> _XScreen:
            """Mirror ``Display.screen()``."""

        def intern_atom(self, name: str) -> object:
            """Mirror ``Display.intern_atom()``."""

        def create_resource_object(self, kind: str, window_id: int) -> _XWindow:
            """Mirror ``Display.create_resource_object()``."""

        def sync(self) -> None:
            """Mirror ``Display.sync()``."""

        def close(self) -> None:
            """Mirror ``Display.close()``."""


_logger = logging.getLogger(__name__)


class XPromptProbe:
    """Looks for allowlisted prompts and raises their top-level windows."""

    def __init__(self) -> None:
        """Start with nothing to repeat."""
        self._last_warning: str | None = None

    def _warn_once(self, message: str) -> None:
        """Warn about a failure, but only when the message changes."""
        if message != self._last_warning:
            _logger.warning("%s", message)
            self._last_warning = message

    def raise_prompts(self) -> tuple[PromptWindow, ...]:
        """Raise every mapped system prompt above everything else.

        Returns:
            The prompts that are on screen and were raised; empty when there
            are none, or when anything went wrong (the lock then stays on top).
        """
        modules = load_xlib("Xlib.display", "Xlib.X", "Xlib.error")
        if modules is None:
            self._warn_once("python-xlib is not installed; cannot look for a prompt")
            return ()
        xdisplay, xconst, xerror = modules
        failures = xlib_failures(xerror)
        try:
            display: _XDisplay = xdisplay.Display()
        except failures as exc:
            self._warn_once(f"cannot open an X connection to look for a prompt: {exc}")
            return ()
        refused: list[object] = []
        try:
            found = _find(display, xconst)
            for prompt in found:
                top = display.create_resource_object("window", prompt.toplevel_id)
                top.configure(stack_mode=xconst.Above, onerror=refused.append)
            display.sync()
        except failures as exc:
            self._warn_once(f"looking for a prompt failed: {exc}")
            return ()
        finally:
            with contextlib.suppress(OSError):
                display.close()
        if refused:
            self._warn_once(f"the X server refused to raise the prompt: {refused[0]}")
            return ()
        self._last_warning = None
        return found


def _find(display: _XDisplay, xconst: ModuleType) -> tuple[PromptWindow, ...]:
    """Every viewable allowlisted window, with its top-level ancestor."""
    root = display.screen().root
    ids: dict[int, None] = {}
    listed = root.get_full_property(
        display.intern_atom("_NET_CLIENT_LIST"), xconst.AnyPropertyType
    )
    if listed is not None:
        ids.update(dict.fromkeys(int(value) for value in listed.value))
    for child in root.query_tree().children:
        ids[child.id] = None
        ids.update(dict.fromkeys(grand.id for grand in child.query_tree().children))
    found: list[PromptWindow] = []
    for window_id in ids:
        window = display.create_resource_object("window", window_id)
        wm_class = window.get_wm_class()
        if not wm_class or not is_system_prompt(wm_class):
            continue
        if window.get_attributes().map_state != xconst.IsViewable:
            continue
        found.append(
            PromptWindow(
                window_id=window_id,
                toplevel_id=_toplevel(window, root.id),
                wm_class=(str(wm_class[0]), str(wm_class[1])),
            )
        )
    return tuple(found)


def _toplevel(window: _XWindow, root_id: int) -> int:
    """The id of ``window``'s ancestor that is a direct child of the root."""
    top = window
    parent = top.query_tree().parent
    while parent.id != root_id:
        top, parent = parent, parent.query_tree().parent
    return top.id
