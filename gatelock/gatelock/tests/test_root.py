"""Tests for GateRoot's safe callback-exception handling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gatelock._root import GateRoot


def _make_root() -> GateRoot:
    """Build a GateRoot without running tk.Tk.__init__ (no display needed)."""
    return GateRoot.__new__(GateRoot)


def _raise_boom() -> None:
    """Raise a ValueError for tests to catch via pytest.raises."""
    msg = "boom"
    raise ValueError(msg)


class TestReportCallbackException:
    """Tests for report_callback_exception."""

    def test_calls_handler_when_set(self) -> None:
        """The configured handler is invoked on a callback error."""
        root = _make_root()
        handler = MagicMock()
        root.on_callback_error = handler

        with pytest.raises(ValueError, match="boom") as exc_info:
            _raise_boom()

        root.report_callback_exception(exc_info.type, exc_info.value, exc_info.tb)

        handler.assert_called_once_with()

    def test_does_not_raise_when_no_handler_set(self) -> None:
        """No handler configured: logs only, never re-raises."""
        root = _make_root()

        with pytest.raises(ValueError, match="boom") as exc_info:
            _raise_boom()

        root.report_callback_exception(exc_info.type, exc_info.value, exc_info.tb)
