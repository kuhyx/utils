# Copyright (c) 2026 Krzysztof Rudnicki
"""Failure handling of :class:`XPromptProbe`: every error fails closed.

Split from ``test_prompts_x.py`` (250-line cap), whose in-memory window tree
and python-xlib stand-ins it reuses.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from gatelock._prompts_x import XPromptProbe
from gatelock.tests.test_prompts_x import (
    ClosedError,
    DisplayError,
    FakeDisplay,
    FakeWindow,
    NoAuthError,
    XError,
    modules,
    probe_over,
)


class TestFailures:
    """Anything going wrong fails closed: no prompt found, lock stays on top."""

    def test_missing_xlib_is_reported_once(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No python-xlib: nothing to do, said once."""
        probe = XPromptProbe()
        with (
            patch("gatelock._prompts_x.load_xlib", return_value=None),
            caplog.at_level(logging.WARNING),
        ):
            assert probe.raise_prompts() == ()
            assert probe.raise_prompts() == ()
        assert caplog.text.count("python-xlib") == 1

    @pytest.mark.parametrize(
        "error",
        [OSError("gone"), DisplayError("no display"), ClosedError(), NoAuthError()],
    )
    def test_no_connection(
        self, error: Exception, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An X connection that will not open is a warning, not a crash."""

        def refuse() -> FakeDisplay:
            raise error

        probe = XPromptProbe()
        with (
            patch("gatelock._prompts_x.load_xlib", return_value=modules(refuse)),
            caplog.at_level(logging.WARNING),
        ):
            assert probe.raise_prompts() == ()
        assert "X connection" in caplog.text

    def test_window_vanishing_mid_scan(self, caplog: pytest.LogCaptureFixture) -> None:
        """BadWindow from a window that went away aborts this scan, once-warned."""
        display = FakeDisplay()
        display.root.add(FakeWindow(display, 10, ("gcr-prompter", "x"))).broken = True
        with probe_over(display) as probe, caplog.at_level(logging.WARNING):
            assert probe.raise_prompts() == ()
            assert probe.raise_prompts() == ()
        assert caplog.text.count("BadWindow") == 1
        assert display.closed

    def test_a_good_scan_rearms_the_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """After a success the same failure is news again."""
        display = FakeDisplay()
        window = display.root.add(FakeWindow(display, 10, ("gcr-prompter", "x")))
        with probe_over(display) as probe, caplog.at_level(logging.WARNING):
            window.broken = True
            probe.raise_prompts()
            window.broken = False
            assert probe.raise_prompts()
            window.broken = True
            probe.raise_prompts()
        assert caplog.text.count("BadWindow") == 2

    def test_raise_refused_is_not_a_yield(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """If the X server rejects the restack, claim nothing."""
        display = FakeDisplay()
        prompt = display.root.add(FakeWindow(display, 10, ("gcr-prompter", "x")))
        prompt.configure_error = XError("BadMatch")
        with probe_over(display) as probe, caplog.at_level(logging.WARNING):
            assert probe.raise_prompts() == ()
        assert "BadMatch" in caplog.text
