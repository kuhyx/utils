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
from gatelock._escape import (
    EscapeDraft,
    EscapeHistory,
    EscapePolicy,
    EscapeTracker,
)
from gatelock._fitcheck import FitResult, measure_fit, report_fit
from gatelock._guards import assert_not_under_pytest, wait_for_x_server
from gatelock._keyboard import bind_activate, bind_cancel, escape_text_tab_trap
from gatelock._outputs import (
    Output,
    OutputEnumerator,
    OutputRect,
    OutputScan,
    enumerate_outputs,
)
from gatelock._randr import RandrBackend
from gatelock._xrandr import parse_xrandr_query
from gatelock._queue import (
    QUEUE_DEADLINE_SECONDS,
    QUEUE_POLL_SECONDS,
    QueueResult,
    stronger_claims,
    wait_for_turn,
)
from gatelock._recovery import RecoveryLoop, RecoveryReport
from gatelock._root import GateRoot
from gatelock._scrollable import ScrollableSurface
from gatelock._surfaces import (
    SurfaceBuilder,
    SurfaceDelta,
    SurfaceInfo,
    SurfaceSet,
    mirror_text_widgets,
    needs_backdrop_root,
)
from gatelock._vt import disable_vt_switching, restore_vt_switching
from gatelock._window import (
    LockConfig,
    LockWindow,
    LockWindowHooks,
    SpaceStep,
    TypeRole,
)
from gatelock.widget_group import WidgetGroup
from gatelock.widgets import (
    DEFAULT_WRAP,
    ButtonStyle,
    ButtonVariant,
    RowStyle,
    heading,
    make_button,
    row,
)

__all__ = [
    "DEFAULT_WRAP",
    "QUEUE_DEADLINE_SECONDS",
    "QUEUE_POLL_SECONDS",
    "RANK_DIET_GUARD",
    "RANK_SCREEN_LOCKER",
    "RANK_WAKE_ALARM",
    "Arbiter",
    "ArbiterVerdict",
    "ButtonStyle",
    "ButtonVariant",
    "Claim",
    "EscapeDraft",
    "EscapeHistory",
    "EscapePolicy",
    "EscapeTracker",
    "FitResult",
    "GateRoot",
    "LockConfig",
    "LockWindow",
    "LockWindowHooks",
    "Output",
    "OutputChangeDetector",
    "OutputEnumerator",
    "OutputRect",
    "OutputScan",
    "QueueResult",
    "RandrBackend",
    "RecoveryLoop",
    "RecoveryReport",
    "RowStyle",
    "ScrollableSurface",
    "SpaceStep",
    "SurfaceBuilder",
    "SurfaceDelta",
    "SurfaceInfo",
    "SurfaceSet",
    "TypeRole",
    "WidgetGroup",
    "assert_not_under_pytest",
    "bind_activate",
    "bind_cancel",
    "default_runtime_dir",
    "disable_vt_switching",
    "enumerate_outputs",
    "escape_text_tab_trap",
    "grab_strength",
    "heading",
    "make_button",
    "measure_fit",
    "mirror_text_widgets",
    "needs_backdrop_root",
    "parse_xrandr_query",
    "report_fit",
    "restore_vt_switching",
    "row",
    "stronger_claims",
    "wait_for_turn",
    "wait_for_x_server",
]
