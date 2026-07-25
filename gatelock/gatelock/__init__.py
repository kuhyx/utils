"""Shared lock-window and HMAC log-integrity backend for blocking-overlay apps.

Used by ``screen-locker``, ``diet-guard`` and ``wake-alarm``, which all need
the same thing: cover every monitor the user can actually see, take the input
grab, and stay up until their own condition is met.
"""

from __future__ import annotations

from gatelock._arbiter import (
    RANK_DIET_GUARD,
    RANK_SCREEN_LOCKER,
    RANK_WAKE_ALARM,
    Arbiter,
    ArbiterVerdict,
    Claim,
    default_runtime_dir,
    grab_strength,
)
from gatelock._detect import OutputChangeDetector
from gatelock._guards import assert_not_under_pytest, wait_for_x_server
from gatelock._outputs import (
    Output,
    OutputEnumerator,
    OutputRect,
    OutputScan,
    RandrBackend,
    enumerate_outputs,
    parse_xrandr_query,
)
from gatelock._recovery import RecoveryLoop, RecoveryReport
from gatelock._root import GateRoot
from gatelock._surfaces import (
    SurfaceBuilder,
    SurfaceDelta,
    SurfaceInfo,
    SurfaceSet,
    mirror_text_widgets,
    needs_backdrop_root,
)
from gatelock._vt import disable_vt_switching, restore_vt_switching
from gatelock._window import LockConfig, LockWindow, LockWindowHooks

__all__ = [
    "RANK_DIET_GUARD",
    "RANK_SCREEN_LOCKER",
    "RANK_WAKE_ALARM",
    "Arbiter",
    "ArbiterVerdict",
    "Claim",
    "GateRoot",
    "LockConfig",
    "LockWindow",
    "LockWindowHooks",
    "Output",
    "OutputChangeDetector",
    "OutputEnumerator",
    "OutputRect",
    "OutputScan",
    "RandrBackend",
    "RecoveryLoop",
    "RecoveryReport",
    "SurfaceBuilder",
    "SurfaceDelta",
    "SurfaceInfo",
    "SurfaceSet",
    "assert_not_under_pytest",
    "default_runtime_dir",
    "disable_vt_switching",
    "enumerate_outputs",
    "grab_strength",
    "mirror_text_widgets",
    "needs_backdrop_root",
    "parse_xrandr_query",
    "restore_vt_switching",
    "wait_for_x_server",
]
