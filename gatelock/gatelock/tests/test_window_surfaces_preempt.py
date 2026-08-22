"""Tests for standing a weaker grab holder down.

Split from ``test_window_surfaces.py`` to hold the shared 250-line cap;
that file keeps arming without a display and the grab-blocked logging.
"""

from __future__ import annotations

import signal
from unittest.mock import MagicMock, patch

from gatelock import _preempt
from gatelock._arbiter import (
    RANK_DIET_GUARD,
    RANK_SCREEN_LOCKER,
    RANK_WAKE_ALARM,
    Claim,
)
from gatelock._detect import _RandrEventSource
from gatelock._outputs import Output, OutputRect
from gatelock._window import LockConfig
from gatelock.tests.conftest import make_window

# Captured before the autouse hermetic fixture replaces it.
REAL_RANDR_START = _RandrEventSource.start

DARK_ONLY = (Output("DP-0", connected=True, rect=None, primary=True),)
TWO_LIVE = (
    Output("DP-0", connected=True, rect=OutputRect(0, 0, 3840, 2160), primary=True),
    Output("HDMI-0", connected=True, rect=OutputRect(3840, 0, 2560, 1440)),
)


class TestPreemptWeakerHolder:
    """A weaker incumbent must not block a stronger claim indefinitely."""

    def _arbiter_with(
        self, *, our_rank: int, holder_rank: int, holder_pid: int
    ) -> MagicMock:
        arbiter = MagicMock()
        arbiter.claim = Claim(
            app="ours",
            rank=our_rank,
            pid=1,
            started="2026-08-21T12:00:00+00:00",
            grab="global",
            disable_vt=True,
            instance_id="ours",
        )
        arbiter.describe_holder.return_value = Claim(
            app="holder",
            rank=holder_rank,
            pid=holder_pid,
            started="2026-08-21T07:04:07+00:00",
            grab="global",
            disable_vt=True,
            instance_id="theirs",
        )
        return arbiter

    def test_signals_a_weaker_holder(self, mock_root: MagicMock) -> None:
        arbiter = self._arbiter_with(
            our_rank=RANK_SCREEN_LOCKER, holder_rank=RANK_DIET_GUARD, holder_pid=4075
        )
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="hard", preempt_weaker_holder=True)
        )
        window._arbiter = arbiter
        with patch("gatelock._preempt.os.kill") as kill:
            window._log_grab_blocked(25)
        kill.assert_called_once_with(4075, signal.SIGTERM)

    def test_never_signals_a_stronger_holder(self, mock_root: MagicMock) -> None:
        arbiter = self._arbiter_with(
            our_rank=RANK_DIET_GUARD, holder_rank=RANK_SCREEN_LOCKER, holder_pid=4137
        )
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="hard", preempt_weaker_holder=True)
        )
        window._arbiter = arbiter
        with patch("gatelock._preempt.os.kill") as kill:
            window._log_grab_blocked(25)
        kill.assert_not_called()

    def test_signals_the_same_holder_only_once(self, mock_root: MagicMock) -> None:
        arbiter = self._arbiter_with(
            our_rank=RANK_SCREEN_LOCKER, holder_rank=RANK_DIET_GUARD, holder_pid=4075
        )
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="hard", preempt_weaker_holder=True)
        )
        window._arbiter = arbiter
        with patch("gatelock._preempt.os.kill") as kill:
            window._log_grab_blocked(25)
            window._log_grab_blocked(50)
        kill.assert_called_once_with(4075, signal.SIGTERM)

    def test_disabled_by_config(self, mock_root: MagicMock) -> None:
        arbiter = self._arbiter_with(
            our_rank=RANK_SCREEN_LOCKER, holder_rank=RANK_DIET_GUARD, holder_pid=4075
        )
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="hard", preempt_weaker_holder=False)
        )
        window._arbiter = arbiter
        with patch("gatelock._preempt.os.kill") as kill:
            window._log_grab_blocked(25)
        kill.assert_not_called()

    def test_off_by_default(self, mock_root: MagicMock) -> None:
        """Preemption is opt-in, so no app can evict anyone by accident.

        wake_alarm outranks screen_locker and builds a plain hard LockConfig.
        While the default was True, that combination SIGTERMed the *armed
        workout lock*, unlocking enforcement with no workout logged.
        """
        arbiter = self._arbiter_with(
            our_rank=RANK_WAKE_ALARM,
            holder_rank=RANK_SCREEN_LOCKER,
            holder_pid=4137,
        )
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        window._arbiter = arbiter
        with patch("gatelock._preempt.os.kill") as kill:
            window._log_grab_blocked(25)
        kill.assert_not_called()

    def test_no_arbiter_means_no_preemption(self, mock_root: MagicMock) -> None:
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="hard", preempt_weaker_holder=True)
        )
        with patch("gatelock._preempt.os.kill") as kill:
            _preempt.maybe_preempt(
                Claim(
                    app="holder",
                    rank=RANK_DIET_GUARD,
                    pid=4075,
                    started="2026-08-21T07:04:07+00:00",
                    grab="global",
                    disable_vt=True,
                    instance_id="theirs",
                ),
                arbiter=None,
                config=window._config,
                preempted_pids=set(),
            )
        kill.assert_not_called()

    def test_a_holder_that_is_already_gone_is_reported_at_info(
        self, mock_root: MagicMock
    ) -> None:
        arbiter = self._arbiter_with(
            our_rank=RANK_SCREEN_LOCKER, holder_rank=RANK_DIET_GUARD, holder_pid=4075
        )
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="hard", preempt_weaker_holder=True)
        )
        window._arbiter = arbiter
        with (
            patch("gatelock._preempt.os.kill", side_effect=ProcessLookupError),
            patch("gatelock._preempt._logger") as logger,
        ):
            window._log_grab_blocked(25)
        assert logger.info.called

    def test_an_unsignalable_holder_is_reported_not_raised(
        self, mock_root: MagicMock
    ) -> None:
        arbiter = self._arbiter_with(
            our_rank=RANK_SCREEN_LOCKER, holder_rank=RANK_DIET_GUARD, holder_pid=4075
        )
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="hard", preempt_weaker_holder=True)
        )
        window._arbiter = arbiter
        with (
            patch("gatelock._preempt.os.kill", side_effect=OSError("nope")),
            patch("gatelock._preempt._logger") as logger,
        ):
            window._log_grab_blocked(25)
        assert logger.exception.called
