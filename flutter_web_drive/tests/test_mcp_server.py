"""MCP server: same verbs as the CLI, delegating to Driver."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from flutter_web_drive import mcp_server
from flutter_web_drive.errors import DriveError

VERBS = {
    "start",
    "stop",
    "shot",
    "tree",
    "tap",
    "tap_xy",
    "text",
    "key",
    "scroll",
    "wait",
    "eval_js",
    "console",
}


class Fake:
    """Driver stand-in: echoes the call, fails on 'stop'."""

    def __init__(self, app: str, *, cdp_port: int | None = None) -> None:
        self.app = app

    def __getattr__(self, name: str) -> Any:
        def verb(*args: Any, **kw: Any) -> str:
            if name == "stop":
                raise DriveError("stop", "boom")
            return f"{self.app}:{name}:{args}:{sorted(kw)}"

        return verb


@pytest.fixture(autouse=True)
def _fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "Driver", Fake)


def _call(tool: str, **args: Any) -> str:
    result = asyncio.run(mcp_server.server.call_tool(tool, args))
    return result.content[0].text  # type: ignore[union-attr]


def test_tools_cover_every_verb() -> None:
    tools = asyncio.run(mcp_server.server.list_tools())
    assert {t.name for t in tools} == VERBS


def test_tools_delegate_to_driver() -> None:
    assert _call("tap", label="Browse", app="k") == "k:tap:('Browse',):['contains']"
    assert _call("start", url="u", profile="/p", cdp_port=1).startswith(
        "default:start:"
    )
    assert _call("shot").startswith("default:shot:(None,)")
    assert _call("shot", out="/x.png").startswith("default:shot:(PosixPath('/x.png'),)")
    assert _call("tree").startswith("default:tree:")
    assert _call("tap_xy", x=1, y=2).startswith("default:tap_xy:(1.0, 2.0)")
    assert _call("text", value="v").startswith("default:text:('v',)")
    assert _call("key", name="Enter").startswith("default:key:")
    assert _call("scroll", dx=0, dy=1).startswith("default:scroll:")
    assert ":scroll:" in _call("scroll", dx=0, dy=1, at_x=2, at_y=3)
    assert _call("wait", label="L").startswith("default:wait:")
    assert _call("eval_js", expr="1").startswith("default:eval:")
    assert _call("console").startswith("default:console:")


def test_text_from_file_keeps_secret_out_of_arguments(tmp_path: Path) -> None:
    secret = tmp_path / "pw"
    secret.write_text("hunter2\n")
    assert _call("text", from_file=str(secret)) == "default:text:('hunter2',):[]"
    with pytest.raises(ToolError, match="cannot read"):
        _call("text", from_file=str(tmp_path / "missing"))
    with pytest.raises(ToolError, match="value or from_file"):
        _call("text")


def test_drive_errors_surface_as_tool_errors() -> None:
    with pytest.raises(ToolError, match="stop failed: boom"):
        _call("stop")


def test_main_runs_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        mcp_server.server, "run", lambda transport: seen.append(transport)
    )
    mcp_server.main()
    assert seen == ["stdio"]
