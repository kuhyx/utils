"""End-to-end tests of ``check.py`` in dist and url mode."""

from __future__ import annotations

import re
import runpy
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from agent_ready.check import main
from agent_ready.tests import sitegen

LINE = re.compile(r"^(PASS|FAIL|SKIP) AR-(FIND|READ|ACT)-\d\d \S")
PKG = Path(__file__).resolve().parents[1]


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, list[str]]:
    """Run the CLI in-process; return exit code and output lines."""
    code = main(list(argv))
    lines = capsys.readouterr().out.splitlines()
    bad = [ln for ln in lines if not LINE.match(ln)]
    assert not bad, bad
    return code, lines


def statuses(lines: list[str], ar_id: str) -> set[str]:
    """Return the set of statuses reported for ``ar_id``."""
    return {ln.split()[0] for ln in lines if ln.split()[1] == ar_id}


def test_dist_good_passes(capsys: pytest.CaptureFixture[str], good_dir: Path) -> None:
    code, lines = run(capsys, "dist", str(good_dir))
    assert code == 0, "\n".join(lines)
    assert not [ln for ln in lines if ln.startswith("FAIL")]
    for ar_id in (
        "AR-FIND-01",
        "AR-FIND-03",
        "AR-FIND-04",
        "AR-READ-01",
        "AR-READ-02",
        "AR-READ-07",
        "AR-READ-09",
    ):
        found = statuses(lines, ar_id)
        assert "PASS" in found and "FAIL" not in found, ar_id
    assert statuses(lines, "AR-READ-11") == {"SKIP"}
    assert statuses(lines, "AR-ACT-10") == {"SKIP"}


def test_dist_bad_fails_every_item(
    capsys: pytest.CaptureFixture[str], bad_dir: Path
) -> None:
    code, lines = run(capsys, "dist", str(bad_dir))
    assert code == 1
    for ar_id in (
        "AR-FIND-01",
        "AR-FIND-03",
        "AR-FIND-04",
        "AR-READ-01",
        "AR-READ-02",
        "AR-READ-03",
        "AR-READ-06",
        "AR-READ-07",
        "AR-READ-08",
        "AR-READ-09",
    ):
        assert "FAIL" in statuses(lines, ar_id), ar_id
    assert any("gptbot" in ln for ln in lines if "AR-FIND-01" in ln)


def test_dist_untagged_code_fails(
    capsys: pytest.CaptureFixture[str], good_dir: Path
) -> None:
    about = good_dir / "about/index.html"
    about.write_text(about.read_text().replace(' class="language-python"', ""))
    code, lines = run(capsys, "dist", str(good_dir))
    assert code == 1
    assert "FAIL" in statuses(lines, "AR-READ-05")


def test_dist_act_opt_in(capsys: pytest.CaptureFixture[str], good_dir: Path) -> None:
    code, lines = run(capsys, "dist", str(good_dir), "--act")
    assert code == 1
    assert "FAIL" in statuses(lines, "AR-ACT-02")


def test_usage_errors(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert main(["dist", str(tmp_path / "missing")]) == 2
    assert main(["url", "not-a-url"]) == 2
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_url_good_passes(
    capsys: pytest.CaptureFixture[str], good_dir: Path, serve: Callable[..., str]
) -> None:
    code, lines = run(capsys, "url", serve(good_dir))
    assert code == 0, "\n".join(lines)
    assert statuses(lines, "AR-READ-02") == {"PASS"}


def test_url_spa_fallback_fails(
    capsys: pytest.CaptureFixture[str], good_dir: Path, serve: Callable[..., str]
) -> None:
    """Every path 200 text/html: a status-only check would wrongly pass."""
    code, lines = run(capsys, "url", serve(good_dir, "spa"))
    assert code == 1
    for ar_id in (
        "AR-FIND-01",
        "AR-FIND-03",
        "AR-FIND-04",
        "AR-READ-01",
        "AR-READ-02",
        "AR-READ-07",
        "AR-READ-09",
    ):
        assert "FAIL" in statuses(lines, ar_id), ar_id
    assert any("text/html" in ln for ln in lines if "AR-FIND-01" in ln)
    assert any(
        "does not exist" in ln for ln in lines if "AR-READ-06" in ln
    )  # HTML fallback != file


def test_url_json_404(
    capsys: pytest.CaptureFixture[str], good_dir: Path, serve: Callable[..., str]
) -> None:
    code, lines = run(capsys, "url", serve(good_dir, "json404"))
    assert code == 1
    assert statuses(lines, "AR-READ-02") == {"PASS"}
    assert "FAIL" in statuses(lines, "AR-FIND-01")


def test_url_blocked_agent(
    capsys: pytest.CaptureFixture[str], good_dir: Path, serve: Callable[..., str]
) -> None:
    code, lines = run(capsys, "url", serve(good_dir, block_ua="GPTBot"))
    assert code == 1
    assert any(ln.startswith("FAIL AR-FIND-01") and "GPTBot" in ln for ln in lines)


def test_url_unreachable_is_3(
    capsys: pytest.CaptureFixture[str], dead_url: str
) -> None:
    assert main(["url", dead_url]) == 3


def test_entry_points_from_other_cwd(good_dir: Path, tmp_path: Path) -> None:
    for cmd in (
        ["bash", str(PKG / "check.sh")],
        [sys.executable, str(PKG / "check.py")],
    ):
        proc = subprocess.run(
            [*cmd, "dist", str(good_dir)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr


def test_dist_checks_every_page_url_caps_visibly(
    capsys: pytest.CaptureFixture[str], good_dir: Path, serve: Callable[..., str]
) -> None:
    """Dist mode ignores --max-pages; url mode names the cap instead of hiding it."""
    sitegen.add_pages(good_dir, 6, broken_last=True)
    code, lines = run(capsys, "dist", str(good_dir), "--max-pages", "3")
    assert code == 1
    assert any(ln.startswith("FAIL AR-READ-01") and "/p5/" in ln for ln in lines)
    code, lines = run(capsys, "url", serve(good_dir), "--max-pages", "3")
    assert any(ln.startswith("SKIP AR-READ-01 checked 3 of 8 pages") for ln in lines), (
        lines
    )


def test_url_act_mcp(
    capsys: pytest.CaptureFixture[str], good_dir: Path, serve: Callable[..., str]
) -> None:
    _, lines = run(capsys, "url", serve(good_dir), "--act")
    assert statuses(lines, "AR-ACT-03") == {"PASS"}
    assert statuses(lines, "AR-ACT-10") == {"PASS"}
    assert "FAIL" in statuses(lines, "AR-ACT-07")
    code, lines = run(capsys, "url", serve(good_dir, "spa"), "--act")
    assert code == 1
    assert statuses(lines, "AR-ACT-03") == {"FAIL"}
    assert statuses(lines, "AR-ACT-10") == {"FAIL"}


def test_script_entry_point_in_process(good_dir: Path) -> None:
    """Run check.py as ``__main__`` here so the guard lines count for coverage."""
    argv = ["check.py", "dist", str(good_dir)]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "argv", argv)
        patch.setattr(sys, "path", list(sys.path))  # check.py prepends to it
        with pytest.raises(SystemExit) as exc:
            runpy.run_path(str(PKG / "check.py"), run_name="__main__")
    assert exc.value.code == 0
