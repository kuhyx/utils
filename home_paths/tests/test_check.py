"""The ~-layout gate: what it must catch, and what it must not.

The "must not" half carries the weight. A gate that fires on prose is a gate
that gets disabled: the first run of this checker returned 189 findings
across ~/src, and every single one outside `todo_desktop.dart` was either a
comment, a macOS branch, vendored third-party code, or a deliberate test
fixture. Each exclusion below is one of those, pinned so it cannot creep
back in.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from home_paths.check import ALLOW_MARKER, main, scan_file, scan_text


def _segments(text: str, name: str = "sample.py") -> list[str]:
    return [f.segment for f in scan_text(Path(name), text)]


# --- the bug this gate exists for -------------------------------------------


def test_catches_the_todo_desktop_regression() -> None:
    """The exact line that served a stale backlog for a day."""
    line = "backlogPath: _argValue(args, '--backlog-path') ?? p.join(home, 'todo', 'BACKLOG.md'),"
    assert _segments(line, "todo_desktop.dart") == ["todo"]


def test_passes_the_fixed_form() -> None:
    assert _segments("p.join(home, 'src', 'todo', 'BACKLOG.md')", "x.dart") == []


@pytest.mark.parametrize(
    ("line", "segment"),
    [
        ('Path.home() / "kuhylog"', "kuhylog"),
        ('Path.home().joinpath("kuhylog")', "kuhylog"),
        ("os.path.join(os.environ['HOME'], 'utils')", "utils"),
        ('expanduser("~/screen-locker")', "screen-locker"),
        ('filepath.Join(home, "octoforge")', "octoforge"),
        ("path.join(os.homedir(), 'signal-bot')", "signal-bot"),
        ('final dir = Directory("$home/todo");', "todo"),
        ('BACKUP="${HOME}/phone_backups"', "phone_backups"),
        ('f"{home}/scanlation-eval"', "scanlation-eval"),
    ],
)
def test_every_construction_spelling(line: str, segment: str) -> None:
    """The rewriter's blind spot was *how* the path was spelled, not which."""
    assert _segments(line) == [segment]


@pytest.mark.parametrize(
    "bucket", ["src", "vendor", "data", "sdk", "media", "Downloads", "Documents"]
)
def test_allowed_buckets_pass(bucket: str) -> None:
    assert _segments(f'Path.home() / "{bucket}" / "thing"') == []


def test_dotfiles_are_not_our_business() -> None:
    assert _segments('Path.home() / ".config" / "todo"') == []
    assert _segments("p.join(home, '.local', 'share', 'todo')", "a.dart") == []


# --- the noise it must not make ---------------------------------------------


def test_comments_are_not_findings() -> None:
    """60% of the first run. `~/utils.` in English is a sentence."""
    assert (
        _segments("# Thin delegate to the shared gate in $HOME/utils, which owns it")
        == []
    )
    assert _segments("// see ${HOME}/todo for the note format", "a.dart") == []


def test_placeholder_segments_are_not_findings() -> None:
    """Docstrings explaining the path grammar say ``$HOME/x``."""
    assert (
        _segments('"""One regex covers ``$HOME/x``, ``${HOME}/x`` and more."""') == []
    )


def test_other_os_home_layouts_are_not_findings() -> None:
    assert _segments('Path.home() / "Library" / "Logs"') == []
    assert _segments('Path.home() / "AppData" / "Roaming"') == []


def test_third_party_and_test_trees_are_skipped(tmp_path: Path) -> None:
    bad = "p.join(home, 'todo', 'x')"
    for rel in (
        "mcp-servers/a.py",
        "vendor/b.py",
        "repo/tests/c.py",
        "repo/test_d.py",
        "repo/e_test.py",
    ):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(bad)
        assert scan_file(target) == [], rel
    plain = tmp_path / "repo" / "real.py"
    plain.write_text(bad)
    assert [f.segment for f in scan_file(plain)] == ["todo"]


def test_allow_marker_is_an_escape_hatch() -> None:
    assert _segments(f"x = home + '/todo'  # {ALLOW_MARKER}: migration note") == []


def test_non_code_and_unreadable_files_yield_nothing(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("p.join(home, 'todo')")
    assert scan_file(tmp_path / "notes.md") == []
    assert scan_file(tmp_path / "missing.py") == []
    binary = tmp_path / "blob.py"
    binary.write_bytes(b"\xff\xfe p.join(home, 'todo')")
    assert scan_file(binary) == []


# --- CLI ---------------------------------------------------------------------


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    clean = tmp_path / "ok.py"
    clean.write_text('Path.home() / "src" / "todo"')
    dirty = tmp_path / "bad.py"
    dirty.write_text('Path.home() / "todo"')

    assert main([]) == 2
    assert main([str(clean)]) == 0
    assert main([str(dirty)]) == 1
    out = capsys.readouterr().out
    assert "builds ~/todo" in out and "Did you mean ~/src/todo?" in out

    assert main(["--all", str(tmp_path)]) == 1
    clean_dir = tmp_path / "clean"
    clean_dir.mkdir()
    (clean_dir / "f.py").write_text("x = 1")
    assert main(["--all", str(clean_dir)]) == 0


def test_render_falls_back_to_absolute_path_outside_root(tmp_path: Path) -> None:
    dirty = tmp_path / "bad.py"
    dirty.write_text('Path.home() / "todo"')
    (finding,) = scan_file(dirty)
    assert finding.render(Path("/nowhere")).startswith(str(dirty))
    assert finding.render(tmp_path).startswith("bad.py:")


def test_walk_prunes_caches_third_party_and_tests(tmp_path: Path) -> None:
    """`--all` must not descend into build output or vendored trees.

    Without this the gate reports on code nobody here owns, which is how the
    first run produced 18 findings about macOS `~/Library` inside a vendored
    Unity MCP server.
    """
    bad = 'Path.home() / "todo"'
    for rel in (
        "build/out.py",
        "node_modules/pkg/index.js",
        ".venv/lib/thing.py",
        "vendor/clone/x.py",
        "pkg/tests/t.py",
        "pkg/test_helper.py",
        "pkg/thing_test.py",
        "notes.md",
    ):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(bad)
    real = tmp_path / "pkg" / "real.py"
    real.write_text(bad)

    assert main(["--all", str(tmp_path)]) == 1
    from home_paths.check import walk

    assert [p.name for p in walk(tmp_path)] == ["real.py"]
