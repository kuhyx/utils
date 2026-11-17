"""Signatures: one per bug, kartka-identical for Dart, generalised for Python and GDScript."""

from __future__ import annotations

from app_errors.signature import normalise, signature, top_frame


def test_dart_crash_matches_kartka_vector() -> None:
    # Vector from kartka_errors.signature (kartka 2026-11-17): moving kartka
    # onto this ingest must not rename its open tickets.
    entry = {
        "kind": "uncaught.flutter",
        "error": "Bad state: no element 42",
        "stack": [
            "#0 List.first (dart:core/list.dart:12:3)",
            "#1 Reader.open (package:kartka/reader/reader.dart:88:7)",
        ],
    }
    sig = signature(entry, app="kartka")
    assert sig.id == "ffcd864656"
    assert sig.type == "StateError"
    assert sig.where == "Reader.open (package:kartka/reader/reader.dart)"


def test_slow_wait_matches_kartka_vector() -> None:
    entry = {
        "kind": "perf.slow",
        "operation": "reader.open",
        "route": "/reader/:id",
        "durationMs": 2100,
    }
    sig = signature(entry, app="kartka")
    assert sig.id == "29a53e8824"
    assert sig.message == "slow wait: reader.open"


def test_slow_wait_ignores_duration() -> None:
    one = {"kind": "perf.slow", "operation": "load", "durationMs": 1100}
    two = {"kind": "perf.slow", "operation": "load", "durationMs": 9000}
    assert signature(one, app="a").id == signature(two, app="a").id


def test_mark_picks_app_frame_and_skips_plumbing() -> None:
    stack = [
        "#0 ErrorReporter.report (package:crdt_sync_flutter/src/errors/error_reporter.dart:5:1)",
        "#1 Home.build (package:todo/home.dart:10:2)",
    ]
    assert top_frame(stack, "package:todo/") == "Home.build (package:todo/home.dart)"


def test_python_frame_line_numbers_dropped() -> None:
    entry = {
        "kind": "uncaught.python",
        "error": "ValueError: bad 12",
        "stack": [
            "gatelock/error_report.py:40 in hook",
            "leetcode_guard/ui.py:123 in solve",
        ],
        "mark": "leetcode_guard/",
    }
    sig = signature(entry, app="leetcode-guard")
    assert sig.where == "leetcode_guard/ui.py in solve"
    assert sig.type == "ValueError"
    assert sig.message == "ValueError: bad <n>"


def test_godot_frame_and_kind_fallback() -> None:
    entry = {
        "kind": "uncaught.gdscript",
        "error": "Invalid access to property 'x'",
        "stack": [
            "res://addons/app_errors/error_reporter.gd:9 in _log",
            "res://scripts/car.gd:77 in _ready",
        ],
        "mark": "res://",
    }
    sig = signature(entry, app="car-rental-sim")
    assert sig.where == "res://scripts/car.gd in _ready"
    assert sig.type == "uncaught.gdscript"


def test_no_frame_falls_back_to_route_then_kind() -> None:
    assert signature({"kind": "ui.snackbar", "error": "x", "route": "/a"}, app="a").where == "route /a"
    assert signature({"kind": "ui.snackbar", "error": "x"}, app="a").where == "kind ui.snackbar"


def test_normalise_masks_volatile_parts() -> None:
    text = "GET https://x.y/z 3f2a9c1d00ff 123e4567-e89b-12d3-a456-426614174000 took 15 s"
    assert normalise(text) == "GET <url> <hex> <uuid> took <n> s"
