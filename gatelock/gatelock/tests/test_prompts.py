# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for the yield-to-system-prompt policy (:mod:`gatelock._prompts`).

Incident 2026-11-11: the GNOME Keyring prompt held the X grab, the lock
covered it, and nothing was clickable. The policy: once the grab has been
blocked for a couple of seconds AND an allowlisted credential prompt is on
screen, raise that prompt above the lock and stop covering it again.
"""

from __future__ import annotations

import logging

import pytest

from gatelock._prompt_names import (
    SYSTEM_PROMPT_CLASSES,
    PromptWindow,
    is_system_prompt,
)
from gatelock._prompts import YIELD_AFTER_S, PromptYield
from gatelock._prompts_x import XPromptProbe

GCR = PromptWindow(
    window_id=11, toplevel_id=10, wm_class=("gcr-prompter", "Gcr-prompter")
)


class FakeClock:
    """A settable monotonic clock."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class FakeProbe:
    """Answers ``raise_prompts`` from a script and counts the calls."""

    def __init__(self, *prompts: PromptWindow) -> None:
        self.prompts = prompts
        self.calls = 0

    def raise_prompts(self) -> tuple[PromptWindow, ...]:
        self.calls += 1
        return self.prompts


class TestAllowlist:
    """Only known credential prompts are ever yielded to."""

    @pytest.mark.parametrize(
        "wm_class",
        [
            ("gcr-prompter", "Gcr-prompter"),
            ("pinentry-gtk-2", "Pinentry-gtk-2"),
            ("pinentry", "Pinentry"),
            (
                "polkit-gnome-authentication-agent-1",
                "Polkit-gnome-authentication-agent-1",
            ),
            ("lxpolkit", "Lxpolkit"),
            ("ssh-askpass", "SSH-Askpass"),
            ("x11-ssh-askpass", "X11-ssh-askpass"),
            ("ksshaskpass", "ksshaskpass"),
            ("gnome-ssh-askpass", "Gnome-ssh-askpass"),
            ("whatever", "GCR-PROMPTER"),
            ("Pinentry-Qt", "x"),
        ],
    )
    def test_known_prompt_matches(self, wm_class: tuple[str, str]) -> None:
        """Instance or class, any case, with the documented globs."""
        assert is_system_prompt(wm_class)

    @pytest.mark.parametrize(
        "wm_class",
        [
            ("steam_game", "Steam_game"),
            ("firefox", "Firefox"),
            ("tk", "Tk"),
            ("pinentr", "x"),
            ("xpinentry", "x"),
            ("", ""),
        ],
    )
    def test_anything_else_does_not(self, wm_class: tuple[str, str]) -> None:
        """A fullscreen game must keep today's behaviour: lock stays on top."""
        assert not is_system_prompt(wm_class)

    def test_the_allowlist_is_one_named_constant(self) -> None:
        """Every pattern the policy approved is in ``SYSTEM_PROMPT_CLASSES``."""
        assert set(SYSTEM_PROMPT_CLASSES) == {
            "gcr-prompter",
            "pinentry*",
            "polkit-gnome-authentication-agent-1",
            "lxpolkit",
            "ssh-askpass*",
            "x11-ssh-askpass",
            "ksshaskpass",
            "gnome-ssh-askpass",
        }

    def test_prompt_window_name(self) -> None:
        """The log names the window by its WM_CLASS instance."""
        assert GCR.name == "gcr-prompter"


class TestYieldPolicy:
    """When the lock steps aside, and when it does not."""

    def _yielder(
        self, *prompts: PromptWindow
    ) -> tuple[PromptYield, FakeClock, FakeProbe]:
        clock, probe = FakeClock(), FakeProbe(*prompts)
        return PromptYield(probe, clock=clock), clock, probe

    def test_default_probe_is_the_xlib_one(self) -> None:
        """Without an explicit probe the real X one is used."""
        assert isinstance(PromptYield()._probe, XPromptProbe)

    def test_idle_before_anything_is_blocked(self) -> None:
        """No failed grab, no look at the screen."""
        policy, _, probe = self._yielder(GCR)
        policy.settle()
        assert not policy.yielding
        assert probe.calls == 0

    def test_waits_out_the_delay(self) -> None:
        """A grab blocked for less than the delay is a blip, not a prompt."""
        policy, clock, probe = self._yielder(GCR)
        policy.grab_blocked("another application has grab")
        clock.now += YIELD_AFTER_S - 0.1
        policy.settle()
        assert not policy.yielding
        assert probe.calls == 0

    def test_yields_to_a_prompt_after_the_delay(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Blocked past the delay with a prompt on screen: yield, and say so."""
        policy, clock, _ = self._yielder(GCR)
        policy.grab_blocked("another application has grab")
        clock.now += YIELD_AFTER_S + 0.1
        with caplog.at_level(logging.WARNING):
            policy.settle()
        assert policy.yielding
        assert policy.prompt_names == ("gcr-prompter",)
        assert "gcr-prompter" in caplog.text

    def test_keeps_raising_it_every_settle(self) -> None:
        """Each tick re-raises the prompt, last, over anything the tick lifted."""
        policy, clock, probe = self._yielder(GCR)
        policy.grab_blocked("x")
        clock.now += 5
        policy.settle()
        policy.settle()
        assert probe.calls == 2
        assert policy.yielding

    def test_no_prompt_means_no_yield(self) -> None:
        """A game holding the grab: the probe finds nothing, the lock stays on top."""
        policy, clock, probe = self._yielder()
        policy.grab_blocked("another application has grab")
        clock.now += 30
        policy.settle()
        assert not policy.yielding
        assert policy.prompt_names == ()
        assert probe.calls == 1

    def test_stops_when_the_prompt_goes_away(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Prompt unmapped but grab still blocked: stack the lock normally again."""
        policy, clock, probe = self._yielder(GCR)
        policy.grab_blocked("x")
        clock.now += 5
        policy.settle()
        probe.prompts = ()
        with caplog.at_level(logging.INFO):
            policy.settle()
        assert not policy.yielding
        assert "gone" in caplog.text

    def test_the_clock_starts_at_the_first_failure(self) -> None:
        """Later failures must not restart the delay."""
        policy, clock, _ = self._yielder(GCR)
        policy.grab_blocked("first")
        clock.now += 1.5
        policy.grab_blocked("second")
        clock.now += 0.6
        policy.settle()
        assert policy.yielding
        assert policy.last_reason == "second"

    def test_grab_held_ends_the_yield_and_says_so(self) -> None:
        """Taking the grab reports whether the lock must now re-raise itself."""
        policy, clock, probe = self._yielder(GCR)
        policy.grab_blocked("x")
        clock.now += 5
        policy.settle()
        assert policy.grab_held() is True
        assert not policy.yielding
        assert policy.prompt_names == ()
        policy.settle()
        assert probe.calls == 1  # nothing blocked any more: no more X work

    def test_grab_held_when_never_yielding(self) -> None:
        """The common case: nothing to undo."""
        policy, _, _ = self._yielder(GCR)
        assert policy.grab_held() is False
        policy.grab_blocked("x")
        assert policy.grab_held() is False
