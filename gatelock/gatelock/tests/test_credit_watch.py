# Copyright (c) 2026 Krzysztof Rudnicki
"""``watch_credit``: a credit that lands while a lock window is up is noticed.

Driven by hand on a ``MagicMock`` root: ``root.after`` records the next poll,
the test runs it, so no display and no real clock are involved.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

import gatelock
from gatelock import CREDIT_POLL_MS, watch_credit

if TYPE_CHECKING:
    from collections.abc import Callable


def _arm(
    paths: list[Path],
    *,
    done: list[bool] | None = None,
    poll_ms: int | None = None,
) -> tuple[MagicMock, MagicMock, MagicMock, Callable[[], None]]:
    """Arm a watch; return (root, is_done, on_credit, run-next-poll)."""
    root = MagicMock()
    verdicts = iter(done if done is not None else [False] * 50)
    is_done = MagicMock(side_effect=lambda: next(verdicts))
    on_credit = MagicMock()
    if poll_ms is None:
        watch_credit(root, paths, is_done, on_credit)
    else:
        watch_credit(root, paths, is_done, on_credit, poll_ms=poll_ms)

    def poll() -> None:
        """Run the callback the last ``root.after`` call scheduled."""
        root.after.call_args.args[1]()

    return root, is_done, on_credit, poll


class TestArming:
    """What arming does before the first poll."""

    def test_exported_from_the_package(self) -> None:
        """The helper is public API, like the other gatelock helpers."""
        assert "watch_credit" in gatelock.__all__
        assert "CREDIT_POLL_MS" in gatelock.__all__

    def test_first_poll_is_scheduled_at_the_default_rate(self, tmp_path: Path) -> None:
        """Nothing is read at arm time; the first poll is one interval away."""
        root, is_done, on_credit, _ = _arm([tmp_path / "log.json"])
        root.after.assert_called_once()
        assert root.after.call_args.args[0] == CREDIT_POLL_MS == 3_000
        is_done.assert_not_called()
        on_credit.assert_not_called()

    def test_custom_poll_rate(self, tmp_path: Path) -> None:
        """``poll_ms`` sets the interval of every poll."""
        root, _, _, poll = _arm([tmp_path / "log.json"], poll_ms=500)
        assert root.after.call_args.args[0] == 500
        poll()
        assert root.after.call_args.args[0] == 500

    def test_no_paths_is_refused(self) -> None:
        """A watch with nothing to stat could never see a change."""
        with pytest.raises(ValueError, match="paths"):
            watch_credit(MagicMock(), [], MagicMock(), MagicMock())

    @pytest.mark.parametrize("poll_ms", [0, -5])
    def test_non_positive_poll_is_refused(self, tmp_path: Path, poll_ms: int) -> None:
        """A zero interval would spin the Tk loop."""
        with pytest.raises(ValueError, match="poll_ms"):
            watch_credit(
                MagicMock(),
                [tmp_path / "a"],
                MagicMock(),
                MagicMock(),
                poll_ms=poll_ms,
            )


class TestPolling:
    """One stat per path per poll; the verdict only when a file moved."""

    def test_first_poll_asks_even_when_the_file_is_absent(self, tmp_path: Path) -> None:
        """A credit may land between startup and arming: ask once up front."""
        root, is_done, on_credit, poll = _arm([tmp_path / "log.json"])
        poll()
        is_done.assert_called_once_with()
        on_credit.assert_not_called()
        assert root.after.call_count == 2

    def test_unchanged_file_is_not_asked_again(self, tmp_path: Path) -> None:
        """Steady state costs one stat per poll and no parse."""
        log = tmp_path / "log.json"
        log.write_text("{}")
        _, is_done, _, poll = _arm([log])
        for _ in range(5):
            poll()
        assert is_done.call_count == 1

    def test_a_changed_file_is_asked_again(self, tmp_path: Path) -> None:
        """A write moves (mtime, size, inode): the verdict is re-read."""
        log = tmp_path / "log.json"
        log.write_text("{}")
        _, is_done, _, poll = _arm([log])
        poll()
        log.write_text('{"meal": 1}')
        poll()
        assert is_done.call_count == 2

    def test_a_replaced_file_is_asked_again(self, tmp_path: Path) -> None:
        """An atomic replace of equal size and mtime still changes the inode."""
        log = tmp_path / "log.json"
        log.write_text("aaaa")
        stamp = log.stat().st_mtime_ns
        _, is_done, _, poll = _arm([log])
        poll()
        replacement = tmp_path / "log.json.tmp"
        replacement.write_text("bbbb")
        os.utime(replacement, ns=(stamp, stamp))
        replacement.replace(log)
        poll()
        assert is_done.call_count == 2

    def test_a_file_appearing_is_asked_again(self, tmp_path: Path) -> None:
        """Absent -> present is a change."""
        log = tmp_path / "log.json"
        _, is_done, _, poll = _arm([log])
        poll()
        log.write_text("{}")
        poll()
        assert is_done.call_count == 2

    def test_any_watched_path_counts(self, tmp_path: Path) -> None:
        """A change in the second file triggers the check too."""
        first, second = tmp_path / "a.json", tmp_path / "b.json"
        first.write_text("{}")
        second.write_text("{}")
        _, is_done, _, poll = _arm([first, second])
        poll()
        second.write_text('{"x": 1}')
        poll()
        assert is_done.call_count == 2


class TestCredit:
    """What happens when the verdict flips."""

    def test_credit_fires_once_and_stops_polling(self, tmp_path: Path) -> None:
        """``on_credit`` runs, and the watch does not re-arm behind it."""
        log = tmp_path / "log.json"
        root, _, on_credit, poll = _arm([log], done=[True])
        poll()
        on_credit.assert_called_once_with()
        assert root.after.call_count == 1

    def test_credit_after_a_later_write(self, tmp_path: Path) -> None:
        """Not done at the first poll, done once the file is rewritten."""
        log = tmp_path / "log.json"
        log.write_text("{}")
        root, _, on_credit, poll = _arm([log], done=[False, True])
        poll()
        on_credit.assert_not_called()
        log.write_text('{"meal": 1}')
        poll()
        on_credit.assert_called_once_with()
        assert root.after.call_count == 2


class TestFailures:
    """One bad read must not end the only thing watching; none is silent."""

    def test_is_done_error_is_logged_and_retried(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A raising check logs, re-arms and asks again without a file change."""
        log = tmp_path / "log.json"
        log.write_text("{}")
        root = MagicMock()
        is_done = MagicMock(side_effect=[ValueError("bad row"), True])
        on_credit = MagicMock()
        watch_credit(root, [log], is_done, on_credit)
        with caplog.at_level(logging.WARNING, logger="gatelock._credit_watch"):
            root.after.call_args.args[1]()
        assert "bad row" in caplog.text
        assert root.after.call_count == 2
        root.after.call_args.args[1]()
        on_credit.assert_called_once_with()

    def test_on_credit_error_is_logged_and_retried(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A close path that raised leaves the window up: keep watching."""
        log = tmp_path / "log.json"
        root = MagicMock()
        on_credit = MagicMock(side_effect=[RuntimeError("close failed"), None])
        watch_credit(root, [log], MagicMock(return_value=True), on_credit)
        with caplog.at_level(logging.WARNING, logger="gatelock._credit_watch"):
            root.after.call_args.args[1]()
        assert "close failed" in caplog.text
        assert root.after.call_count == 2
        root.after.call_args.args[1]()
        assert on_credit.call_count == 2

    def test_stat_error_keeps_the_lock_and_retries(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An unreadable file is "could not check": logged, never "done"."""
        log = tmp_path / "log.json"
        log.write_text("{}")
        _, is_done, on_credit, poll = _arm([log], done=[True])
        with (
            patch.object(Path, "stat", side_effect=PermissionError("denied")),
            caplog.at_level(logging.WARNING, logger="gatelock._credit_watch"),
        ):
            poll()
        assert "denied" in caplog.text
        is_done.assert_not_called()
        on_credit.assert_not_called()
        poll()
        on_credit.assert_called_once_with()
