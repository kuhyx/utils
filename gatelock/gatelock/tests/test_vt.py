"""Tests for VT-switch disable/restore."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from gatelock._vt import disable_vt_switching, restore_vt_switching

_SETXKBMAP = "/usr/bin/setxkbmap"


class TestDisableVtSwitching:
    """Tests for disable_vt_switching."""

    def test_runs_setxkbmap_and_returns_true(
        self, mock_subprocess_run: MagicMock
    ) -> None:
        """Disables VT switching and reports success when setxkbmap exists."""
        result = disable_vt_switching()

        assert result is True
        mock_subprocess_run.assert_called_once_with(
            [_SETXKBMAP, "-option", "srvrkeys:none"],
            check=False,
        )

    def test_returns_false_when_setxkbmap_missing(self) -> None:
        """No subprocess call and returns False when setxkbmap is unavailable."""
        with (
            patch("gatelock._vt.shutil.which", return_value=None),
            patch("gatelock._vt.subprocess.run") as mock_run,
        ):
            result = disable_vt_switching()

        assert result is False
        mock_run.assert_not_called()


class TestRestoreVtSwitching:
    """Tests for restore_vt_switching."""

    def test_runs_setxkbmap(self, mock_subprocess_run: MagicMock) -> None:
        """Restores VT switching when setxkbmap exists."""
        restore_vt_switching()

        mock_subprocess_run.assert_called_once_with(
            [_SETXKBMAP, "-option", ""],
            check=False,
        )

    def test_no_call_when_setxkbmap_missing(self) -> None:
        """No subprocess call when setxkbmap is unavailable."""
        with (
            patch("gatelock._vt.shutil.which", return_value=None),
            patch("gatelock._vt.subprocess.run") as mock_run,
        ):
            restore_vt_switching()

        mock_run.assert_not_called()
