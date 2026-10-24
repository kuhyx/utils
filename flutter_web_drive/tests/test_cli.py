"""CLI: argument parsing, verb dispatch, exit codes and stderr messages."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, ClassVar

import pytest

from flutter_web_drive import cli
from flutter_web_drive.errors import EXIT_BROWSER, EXIT_USAGE, DriveError


class Recorder:
    """Stands in for Driver: records each call and returns its name."""

    instances: ClassVar[list[Recorder]] = []

    def __init__(self, app: str, *, cdp_port: int | None = None) -> None:
        self.app = app
        self.cdp_port = cdp_port
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        Recorder.instances.append(self)

    def __getattr__(self, name: str) -> Any:
        def verb(*args: Any, **kw: Any) -> str:
            self.calls.append((name, args, kw))
            if name == "stop":
                raise DriveError("stop", "boom", EXIT_BROWSER)
            return f"ok {name}"

        return verb


@pytest.fixture(autouse=True)
def _recorder(monkeypatch: pytest.MonkeyPatch) -> None:
    Recorder.instances = []
    monkeypatch.setattr(cli, "Driver", Recorder)


def _run(argv: list[str], stdin: str = "") -> tuple[int, Any]:
    code = cli.main(argv, stdin=io.StringIO(stdin))
    return code, Recorder.instances[-1].calls[-1] if Recorder.instances else None


@pytest.mark.parametrize(
    ("argv", "call"),
    [
        (
            ["start", "--url", "http://u/", "--profile", "/p", "--cdp-port", "9341"],
            (
                "start",
                ("http://u/", Path("/p"), 9341),
                {"unit": None, "size": "1400x1000"},
            ),
        ),
        (["shot"], ("shot", (None,), {"min_colours": 0})),
        (
            ["shot", "o.png", "--min-colours", "2"],
            ("shot", (Path("o.png"),), {"min_colours": 2}),
        ),
        (
            ["tree", "--filter", "x", "--all", "--row", "R"],
            ("tree", (), {"filt": "x", "show_all": True, "row": "R"}),
        ),
        (["tap", "Browse", "--contains"], ("tap", ("Browse",), {"contains": True})),
        (["tap-xy", "1", "2.5"], ("tap_xy", (1.0, 2.5), {})),
        (["text", "hello"], ("text", ("hello",), {})),
        (["key", "Enter"], ("key", ("Enter",), {})),
        (["scroll", "0", "300"], ("scroll", (0.0, 300.0), {"at": None})),
        (
            ["scroll", "0", "3", "--at", "4", "5"],
            ("scroll", (0.0, 3.0), {"at": (4.0, 5.0)}),
        ),
        (
            ["wait", "Library", "--timeout", "3", "--gone", "--flag", "current"],
            (
                "wait",
                ("Library",),
                {
                    "timeout": 3.0,
                    "contains": False,
                    "gone": True,
                    "flag": "current",
                    "row": None,
                },
            ),
        ),
        (["eval", "1+1"], ("eval", ("1+1",), {})),
        (
            ["console", "--limit", "5", "--warnings", "--fail-on-error"],
            ("console", (), {"limit": 5, "warnings": True, "fail_on_error": True}),
        ),
    ],
)
def test_verbs_dispatch(
    argv: list[str], call: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    code, got = _run(argv)
    assert code == 0
    assert got == call
    assert capsys.readouterr().out.startswith("ok ")


def test_global_app_and_port() -> None:
    cli.main(["--app", "kartka", "--cdp-port", "9", "tree"], stdin=io.StringIO())
    assert (Recorder.instances[-1].app, Recorder.instances[-1].cdp_port) == (
        "kartka",
        9,
    )


def test_app_defaults_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FWD_APP", "envapp")
    cli.main(["tree"], stdin=io.StringIO())
    assert Recorder.instances[-1].app == "envapp"


def test_text_stdin_strips_one_trailing_newline() -> None:
    _, call = _run(["text", "--stdin"], stdin="p@ss\n")
    assert call == ("text", ("p@ss",), {})


def test_text_file_reads_secret_without_argv(tmp_path: Path) -> None:
    secret = tmp_path / "pw"
    secret.write_text("s3cret\n")
    _, call = _run(["text", "--file", str(secret)])
    assert call == ("text", ("s3cret",), {})


def test_text_file_missing_is_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        cli.main(["text", "--file", str(tmp_path / "nope")], stdin=io.StringIO())
        == EXIT_USAGE
    )
    assert "cannot read" in capsys.readouterr().err


def test_text_needs_value_or_stdin(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["text"], stdin=io.StringIO()) == EXIT_USAGE
    assert "text needs a value, --stdin or --file" in capsys.readouterr().err


def test_drive_error_becomes_exit_code_and_one_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, _ = _run(["stop"])
    assert code == EXIT_BROWSER
    assert capsys.readouterr().err == "flutter_web_drive: stop failed: boom\n"


def test_usage_errors_exit_2() -> None:
    with pytest.raises(SystemExit) as err:
        cli.main(["bogus"], stdin=io.StringIO())
    assert err.value.code == EXIT_USAGE
