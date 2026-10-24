"""Stdio MCP server exposing the driver's verbs as tools (thin: every tool is one Driver call).

Register (user scope) with:
    claude mcp add flutter-web-drive -s user -e PYTHONPATH=$HOME/src/utils \
        -- python3 -m flutter_web_drive.mcp_server
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from flutter_web_drive.api import Driver
from flutter_web_drive.errors import DriveError

server = MCPServer(
    "flutter-web-drive",
    instructions=(
        "Drive a Flutter web app in a private headless chromium (never the user's screen). "
        "start once, then tree -> tap/text/key/scroll -> wait -> shot. Widgets are addressed "
        "by their semantics label as shown by `tree`. `app` namespaces state per app."
    ),
)


def _run(app: str, call: Callable[[Driver], str]) -> str:
    """Run one verb; a DriveError becomes a tool error naming the failing step."""
    try:
        return call(Driver(app))
    except DriveError as err:
        raise ToolError(f"{err.step} failed: {err.message}") from err


@server.tool()
def start(
    url: str,
    profile: str,
    cdp_port: int,
    app: str = "default",
    unit: str | None = None,
    size: str = "1400x1000",
) -> str:
    """Launch (or reuse) a headless chromium unit on url with a persistent profile dir."""
    return _run(
        app, lambda d: d.start(url, Path(profile), cdp_port, unit=unit, size=size)
    )


@server.tool()
def stop(app: str = "default") -> str:
    """Stop the app's headless chromium unit (profile kept)."""
    return _run(app, lambda d: d.stop())


@server.tool()
def shot(out: str | None = None, min_colours: int = 0, app: str = "default") -> str:
    """Screenshot the viewport to a PNG; returns 'path WxH colours=N stddev=S'."""
    return _run(
        app, lambda d: d.shot(Path(out) if out else None, min_colours=min_colours)
    )


@server.tool()
def tree(
    filt: str | None = None,
    show_all: bool = False,
    row: str | None = None,
    app: str = "default",
) -> str:
    """List semantics nodes: '#id role "label" = "value" [tap,current,...] @x,y wxh'. row: only the row of that label."""
    return _run(app, lambda d: d.tree(filt=filt, show_all=show_all, row=row))


@server.tool()
def tap(label: str, contains: bool = False, app: str = "default") -> str:
    """Click the node with this label (exact label or one of its lines; contains=substring)."""
    return _run(app, lambda d: d.tap(label, contains=contains))


@server.tool()
def tap_xy(x: float, y: float, app: str = "default") -> str:
    """Click at viewport CSS-pixel coordinates."""
    return _run(app, lambda d: d.tap_xy(x, y))


@server.tool()
def text(
    value: str | None = None, from_file: str | None = None, app: str = "default"
) -> str:
    """Insert text into the focused field. Use from_file for secrets so they never appear in the transcript."""
    if from_file:
        try:
            value = Path(from_file).read_text().removesuffix("\n")
        except OSError as exc:
            raise ToolError(
                f"text failed: cannot read {from_file}: {exc.strerror}"
            ) from exc
    if value is None:
        raise ToolError("text failed: pass value or from_file")
    secret = value
    return _run(app, lambda d: d.text(secret))


@server.tool()
def key(name: str, app: str = "default") -> str:
    """Press a key: Enter, Escape, Tab, Backspace, Delete, Space, Arrow*, Home, End, PageUp, PageDown."""
    return _run(app, lambda d: d.key(name))


@server.tool()
def scroll(
    dx: float,
    dy: float,
    at_x: float | None = None,
    at_y: float | None = None,
    app: str = "default",
) -> str:
    """Mouse-wheel scroll by (dx, dy) at (at_x, at_y), default viewport center."""
    at = (at_x, at_y) if at_x is not None and at_y is not None else None
    return _run(app, lambda d: d.scroll(dx, dy, at=at))


@server.tool()
def wait(
    label: str,
    timeout: float = 10.0,
    contains: bool = False,
    gone: bool = False,
    flag: str | None = None,
    row: str | None = None,
    app: str = "default",
) -> str:
    """Poll until a label (carrying flag, e.g. current/checked) is present, or absent with gone; timeout <= 50 s, screenshot on failure."""
    return _run(
        app,
        lambda d: d.wait(
            label, timeout=timeout, contains=contains, gone=gone, flag=flag
        ),
    )


@server.tool()
def eval_js(expr: str, app: str = "default") -> str:
    """Evaluate JavaScript in the page; returns the JSON value."""
    return _run(app, lambda d: d.eval(expr))


@server.tool()
def console(
    limit: int = 20,
    warnings: bool = False,
    fail_on_error: bool = False,
    app: str = "default",
) -> str:
    """Console errors (and optionally warnings) since page load."""
    return _run(
        app,
        lambda d: d.console(
            limit=limit, warnings=warnings, fail_on_error=fail_on_error
        ),
    )


def main() -> None:
    """Serve over stdio."""
    server.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover - exercised by the stdio smoke test
    main()
