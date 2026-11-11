# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for finding and raising a credential prompt over python-xlib.

python-xlib is optional and there is no X server in the suite, so the library
is replaced by a small in-memory window tree. The real thing is exercised by
``scripts/verify_prompt_yield.py`` on a private Xvfb.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import patch

from gatelock._prompts_x import XPromptProbe

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from gatelock._prompt_names import PromptWindow

ABOVE = 0
ANY = 0
VIEWABLE = 2


class XError(Exception):
    """Stands in for ``Xlib.error.XError``."""


class DisplayError(Exception):
    """Stands in for ``Xlib.error.DisplayError``."""


class ClosedError(Exception):
    """Stands in for ``Xlib.error.ConnectionClosedError``."""


class NoAuthError(Exception):
    """Stands in for ``Xlib.error.XauthError``."""


class FakeWindow:
    """One node of the fake window tree."""

    def __init__(
        self,
        display: FakeDisplay,
        wid: int,
        wm_class: tuple[str, str] | None = None,
        *,
        viewable: bool = True,
    ) -> None:
        self.display = display
        self.id = wid
        self.wm_class = wm_class
        self.viewable = viewable
        self.parent: FakeWindow | None = None
        self.children: list[FakeWindow] = []
        self.client_list: list[int] | None = None
        self.raised = False
        self.broken = False
        self.configure_error: XError | None = None
        display.windows[wid] = self

    def add(self, child: FakeWindow) -> FakeWindow:
        child.parent = self
        self.children.append(child)
        return child

    def get_wm_class(self) -> tuple[str, str] | None:
        if self.broken:
            message = "BadWindow"
            raise XError(message)
        return self.wm_class

    def get_attributes(self) -> SimpleNamespace:
        return SimpleNamespace(map_state=VIEWABLE if self.viewable else 0)

    def query_tree(self) -> SimpleNamespace:
        return SimpleNamespace(children=list(self.children), parent=self.parent)

    def get_full_property(self, atom: str, _kind: int) -> SimpleNamespace | None:
        if atom != "_NET_CLIENT_LIST" or self.client_list is None:
            return None
        return SimpleNamespace(value=self.client_list)

    def configure(self, *, stack_mode: int, onerror: Callable[[XError], None]) -> None:
        assert stack_mode == ABOVE
        self.raised = True
        if self.configure_error is not None:
            onerror(self.configure_error)


class FakeDisplay:
    """The slice of ``Xlib.display.Display`` the probe uses."""

    def __init__(self) -> None:
        self.windows: dict[int, FakeWindow] = {}
        self.root = FakeWindow(self, 1)
        self.closed = False
        self.synced = False

    def screen(self) -> SimpleNamespace:
        return SimpleNamespace(root=self.root)

    def intern_atom(self, name: str) -> str:
        return name

    def create_resource_object(self, _kind: str, wid: int) -> FakeWindow:
        return self.windows[wid]

    def sync(self) -> None:
        self.synced = True

    def close(self) -> None:
        self.closed = True


def modules(display_factory: Callable[[], FakeDisplay]) -> tuple[SimpleNamespace, ...]:
    """What ``load_xlib("Xlib.display", "Xlib.X", "Xlib.error")`` returns."""
    return (
        SimpleNamespace(Display=display_factory),
        SimpleNamespace(Above=ABOVE, AnyPropertyType=ANY, IsViewable=VIEWABLE),
        SimpleNamespace(
            DisplayError=DisplayError,
            XauthError=NoAuthError,
            ConnectionClosedError=ClosedError,
            XError=XError,
        ),
    )


@contextmanager
def probe_over(display: FakeDisplay) -> Iterator[XPromptProbe]:
    """A probe whose X connection is ``display``."""
    loaded = modules(lambda: display)
    with patch("gatelock._prompts_x.load_xlib", return_value=loaded):
        yield XPromptProbe()


def scan(display: FakeDisplay) -> tuple[PromptWindow, ...]:
    """One ``raise_prompts()`` over ``display``."""
    with probe_over(display) as probe:
        return probe.raise_prompts()


class TestFinding:
    """Which windows count, and what gets raised."""

    def test_framed_client_raises_the_frame(self) -> None:
        """i3 reparents: the class is on the client, the frame is the top-level."""
        display = FakeDisplay()
        frame = display.root.add(FakeWindow(display, 10, ("i3-frame", "i3-frame")))
        client = frame.add(FakeWindow(display, 11, ("gcr-prompter", "Gcr-prompter")))
        found = scan(display)
        assert [(p.window_id, p.toplevel_id) for p in found] == [(11, 10)]
        assert frame.raised
        assert not client.raised
        assert display.synced
        assert display.closed

    def test_unframed_client_is_its_own_toplevel(self) -> None:
        """Without a window manager the prompt is a direct root child."""
        display = FakeDisplay()
        prompt = display.root.add(
            FakeWindow(display, 20, ("pinentry-gtk-2", "Pinentry"))
        )
        found = scan(display)
        assert [(p.window_id, p.toplevel_id) for p in found] == [(20, 20)]
        assert prompt.raised

    def test_net_client_list_is_used_and_deduplicated(self) -> None:
        """A client listed by the WM and also found in the tree is raised once."""
        display = FakeDisplay()
        frame = display.root.add(FakeWindow(display, 10))
        frame.add(FakeWindow(display, 11, ("gcr-prompter", "x")))
        display.root.client_list = [11, 11]
        found = scan(display)
        assert [p.window_id for p in found] == [11]

    def test_net_client_list_alone_finds_a_deeper_window(self) -> None:
        """A client the tree walk would not reach is still found via the WM list."""
        display = FakeDisplay()
        outer = display.root.add(FakeWindow(display, 10))
        mid = outer.add(FakeWindow(display, 11))
        deep = mid.add(FakeWindow(display, 12, ("lxpolkit", "Lxpolkit")))
        display.root.client_list = [12]
        found = scan(display)
        assert [(p.window_id, p.toplevel_id) for p in found] == [(12, 10)]
        assert outer.raised
        assert not deep.raised

    def test_unmapped_prompt_is_ignored(self) -> None:
        """A prompt on another workspace is not on screen: leave the lock alone."""
        display = FakeDisplay()
        display.root.add(FakeWindow(display, 10, ("gcr-prompter", "x"), viewable=False))
        assert scan(display) == ()

    def test_other_windows_are_ignored(self) -> None:
        """No class, or a class off the allowlist, is not a prompt."""
        display = FakeDisplay()
        display.root.add(FakeWindow(display, 10, ("steam_game", "Steam")))
        display.root.add(FakeWindow(display, 11, None))
        found = scan(display)
        assert found == ()
        assert not display.windows[10].raised
        assert display.closed
