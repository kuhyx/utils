"""Shared lock-window and HMAC log-integrity backend for blocking-overlay apps."""

from __future__ import annotations

from gatelock._root import GateRoot
from gatelock._vt import disable_vt_switching, restore_vt_switching
from gatelock._window import LockConfig, LockWindow, LockWindowHooks

__all__ = [
    "GateRoot",
    "LockConfig",
    "LockWindow",
    "LockWindowHooks",
    "disable_vt_switching",
    "restore_vt_switching",
]
