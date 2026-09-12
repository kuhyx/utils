"""The gate entry point: counting, skipping, git-ignore, and exit codes."""

from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from file_length import check
from file_length.repo_exempt import EXEMPT_FILE
from file_length.tests.conftest import lines, write


def run_main(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["check.py", *argv])
    return check.main()


def test_count_lines_variants(tmp_path: Path) -> None:
    assert check.count_lines(write(tmp_path, "a.py", lines(3))) == 3
    assert check.count_lines(write(tmp_path, "b.py", "no newline")) == 1
    assert check.count_lines(write(tmp_path, "c.py", "")) == 0
    binary = tmp_path / "d.py"
    binary.write_bytes(b"ab\x00cd\n")
    assert check.count_lines(binary) is None
    assert check.count_lines(tmp_path / "missing.py") is None


def test_count_lines_spans_chunks(tmp_path: Path) -> None:
    big = tmp_path / "big.py"
    big.write_bytes(b"x\n" * (1 << 20))
    assert check.count_lines(big) == 1 << 20


def test_absolutize(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    assert check.absolutize(Path("a.py")) == tmp_path / "a.py"
    assert check.absolutize(tmp_path / "b.py") == tmp_path / "b.py"


def test_exempt_reasons(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert check.exempt_reason(Path("x.html"), 1) == "not a capped extension"
    assert check.exempt_reason(Path("node_modules/x.js"), 1) == "vendored / third-party"
    write(repo, EXEMPT_FILE, "tags/*.kt  # tag tables\n")
    assert check.exempt_reason(Path("tags/A.kt"), 1) == "repo exemption: tag tables"
    art = Path("docs/superpowers/plans/p.md")
    assert check.exempt_reason(art, 1) == "frozen session artifact"
    assert check.exempt_reason(Path("m.g.dart"), 1) == "generated"
    words = write(repo, "w.txt", "a\n" * 10)
    assert check.exempt_reason(words, 10) == "data-ish text (wordlist)"
    code = write(repo, "c.py", lines(3))
    assert check.exempt_reason(code, 3) is None

    def boom(_self: Path) -> None:
        raise OSError("gone")

    monkeypatch.setattr(Path, "stat", boom)
    assert check.exempt_reason(Path("c.py"), 3) == "unreadable"


def test_git_ignored(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(repo, ".gitignore", "*.log\n")
    kept = write(repo, "a.py", "x\n")
    dropped = write(repo, "b.log", "x\n")
    assert check.git_ignored([], repo) == set()
    assert check.git_ignored([kept, dropped], repo) == {dropped}
    assert check.git_ignored([kept], repo.parent / "not-a-repo-xyz") == set()

    def no_git(*_a: object, **_k: object) -> None:
        raise OSError("no git")

    monkeypatch.setattr(subprocess, "run", no_git)
    assert check.git_ignored([kept], repo) == set()


def test_iter_all_skips_excluded_ignored_and_symlinks(repo: Path) -> None:
    write(repo, ".gitignore", "out/\n")
    keep = write(repo, "src/a.py", "x\n")
    write(repo, "node_modules/b.py", "x\n")
    write(repo, "out/c.py", "x\n")
    (repo / "link.py").symlink_to(keep)
    found = set(check.iter_all(repo))
    assert keep in found
    assert not any(p.name in {"b.py", "c.py", "link.py"} for p in found)


def test_main_requires_paths_or_all(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit) as exc:
        run_main(monkeypatch)
    assert exc.value.code == 2


def test_main_all_reports_violations_sorted(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, "small.py", lines(10))
    write(repo, "mid.py", lines(260))
    write(repo, "huge.py", lines(400))
    write(repo, "skip.g.dart", lines(400))
    assert run_main(monkeypatch, "--all", "--explain") == 1
    out, err = capsys.readouterr()
    assert "skip" in out and "generated" in out
    assert err.index("huge.py") < err.index("mid.py")
    assert "small.py" not in err


def test_main_paths_honour_gitignore_and_missing(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(repo, ".gitignore", "*.log\n")
    write(repo, "a.log", lines(300))
    write(repo, "b.py", lines(300))
    assert run_main(monkeypatch, "a.log", "missing.py") == 0
    assert run_main(monkeypatch, "b.py") == 1


def test_main_skips_binary_and_honours_repo_exemption(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / "blob.py").write_bytes(b"\x00" * 10)
    write(repo, "tags/Big.kt", lines(6000))
    write(repo, EXEMPT_FILE, "tags/*.kt  # tag data tables\n")
    assert run_main(monkeypatch, "--all") == 0


def test_main_fails_closed_on_malformed_exempt_file(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, EXEMPT_FILE, "tags/*.kt\n")
    assert run_main(monkeypatch, "--all") == 2
    assert "File-length gate ERROR" in capsys.readouterr().err


def test_main_tolerates_a_file_vanishing_mid_run(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(check, "iter_all", lambda _root: [repo / "gone.py"])
    assert run_main(monkeypatch, "--all") == 0


def test_runs_as_a_plain_script(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(repo, "ok.py", lines(3))
    monkeypatch.setattr(sys, "argv", ["check.py", "--all"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(Path(check.__file__)), run_name="__main__")
    assert exc.value.code == 0
