"""``python -m flutter_web_drive [--app A] <verb> ...``: one verb per call, exit code is the verdict."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, TextIO

from flutter_web_drive.api import Driver
from flutter_web_drive.errors import EXIT_OK, EXIT_USAGE, DriveError


class _Parser(argparse.ArgumentParser):
    """argparse that exits with our usage code (2 already, but explicit)."""

    def error(self, message: str) -> Any:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"flutter_web_drive: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    """All verbs and flags."""
    p = _Parser(prog="flutter_web_drive", description=__doc__)
    p.add_argument(
        "--app",
        default=os.environ.get("FWD_APP", "default"),
        help="state/artefact namespace",
    )
    p.add_argument("--cdp-port", type=int, help="override the port saved by start")
    sub = p.add_subparsers(dest="verb", required=True)

    s = sub.add_parser("start", help="launch the headless unit on a URL")
    s.add_argument("--url", required=True)
    s.add_argument("--profile", required=True, type=Path)
    s.add_argument("--cdp-port", dest="start_port", required=True, type=int)
    s.add_argument("--unit")
    s.add_argument("--size", default="1400x1000")
    sub.add_parser("stop", help="stop the unit (profile kept)")
    s = sub.add_parser("shot", help="screenshot the viewport")
    s.add_argument("out", nargs="?", type=Path)
    s.add_argument(
        "--min-colours", type=int, default=0, help="fail if fewer distinct colours"
    )
    s = sub.add_parser("tree", help="list semantics nodes")
    s.add_argument("--filter", dest="filt")
    s.add_argument(
        "--all", dest="show_all", action="store_true", help="include bare containers"
    )
    s.add_argument("--row", help="only nodes in the row of the node with this label")
    s = sub.add_parser("tap", help="click a node by label")
    s.add_argument("label")
    s.add_argument("--contains", action="store_true")
    s = sub.add_parser("tap-xy", help="click at viewport coordinates")
    s.add_argument("x", type=float)
    s.add_argument("y", type=float)
    s = sub.add_parser("text", help="insert text into the focused field")
    s.add_argument("value", nargs="?")
    s.add_argument(
        "--stdin", action="store_true", help="read the text from stdin (secrets)"
    )
    s.add_argument("--file", type=Path, help="read the text from a file (secrets)")
    s = sub.add_parser("key", help="press Enter, Escape, Tab, Backspace, ...")
    s.add_argument("name")
    s = sub.add_parser("scroll", help="mouse-wheel scroll")
    s.add_argument("dx", type=float)
    s.add_argument("dy", type=float)
    s.add_argument("--at", nargs=2, type=float, metavar=("X", "Y"))
    s = sub.add_parser("wait", help="poll until a label is present (or --gone)")
    s.add_argument("label")
    s.add_argument("--timeout", type=float, default=10.0)
    s.add_argument("--contains", action="store_true")
    s.add_argument("--gone", action="store_true")
    s.add_argument("--row", help="search only the row of the node with this label")
    s.add_argument(
        "--flag",
        help="the node must carry this flag (current, selected, checked, focused, ...)",
    )
    s = sub.add_parser("eval", help="evaluate JS, print JSON")
    s.add_argument("expr")
    s = sub.add_parser("console", help="console errors since page load")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--warnings", action="store_true")
    s.add_argument("--fail-on-error", action="store_true")
    return p


def _text_value(ns: argparse.Namespace, stdin: TextIO) -> str:
    if ns.file is not None:
        try:
            return ns.file.read_text().removesuffix("\n")
        except OSError as exc:
            raise DriveError(
                "text", f"cannot read {ns.file}: {exc.strerror}", EXIT_USAGE
            ) from exc
    if ns.stdin:
        return stdin.read().removesuffix("\n")
    if ns.value is None:
        raise DriveError("text", "text needs a value, --stdin or --file", EXIT_USAGE)
    return str(ns.value)


def dispatch(drv: Driver, ns: argparse.Namespace, stdin: TextIO) -> str:
    """Call the Driver method for the parsed verb."""
    verb = ns.verb
    if verb == "start":
        return drv.start(ns.url, ns.profile, ns.start_port, unit=ns.unit, size=ns.size)
    if verb == "stop":
        return drv.stop()
    if verb == "shot":
        return drv.shot(ns.out, min_colours=ns.min_colours)
    if verb == "tree":
        return drv.tree(filt=ns.filt, show_all=ns.show_all, row=ns.row)
    if verb == "tap":
        return drv.tap(ns.label, contains=ns.contains)
    if verb == "tap-xy":
        return drv.tap_xy(ns.x, ns.y)
    if verb == "text":
        return drv.text(_text_value(ns, stdin))
    if verb == "key":
        return drv.key(ns.name)
    if verb == "scroll":
        return drv.scroll(ns.dx, ns.dy, at=tuple(ns.at) if ns.at else None)
    if verb == "wait":
        return drv.wait(
            ns.label,
            timeout=ns.timeout,
            contains=ns.contains,
            gone=ns.gone,
            flag=ns.flag,
            row=ns.row,
        )
    if verb == "eval":
        return drv.eval(ns.expr)
    return drv.console(
        limit=ns.limit, warnings=ns.warnings, fail_on_error=ns.fail_on_error
    )


def main(argv: list[str] | None = None, *, stdin: TextIO = sys.stdin) -> int:
    """Parse, run one verb, print its result; failures print one line to stderr."""
    ns = build_parser().parse_args(argv)
    drv = Driver(ns.app, cdp_port=ns.cdp_port)
    try:
        print(dispatch(drv, ns, stdin))
    except DriveError as err:
        print(f"flutter_web_drive: {err.step} failed: {err.message}", file=sys.stderr)
        return err.code
    return EXIT_OK
