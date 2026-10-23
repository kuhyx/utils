"""Tests for scripts/link_leetcode_coach.sh, the install step for the coach.

Run against a throwaway HOME: the script must never be pointed at the real
~/.claude from a test.
"""

from __future__ import annotations

from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "link_leetcode_coach.sh"
COACH = REPO / "leetcode_coach"


def _run(home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT)],
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )


def _old_skill(home: Path) -> Path:
    old = home / ".claude" / "skills" / "leetcode"
    old.mkdir(parents=True)
    (old / "SKILL.md").write_text("---\nname: leetcode\n---\n", encoding="utf-8")
    (old / "leetcode_repl.py").write_text("", encoding="utf-8")
    return old


def test_fresh_home_gets_both_links(tmp_path: Path) -> None:
    proc = _run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    skill = tmp_path / ".claude" / "skills" / "leetcode"
    assert skill.is_symlink()
    assert skill.resolve() == COACH
    assert (tmp_path / ".local" / "bin" / "leetcode").resolve() == COACH / "leetcode"
    assert _run(tmp_path).returncode == 0  # idempotent


def test_old_skill_dir_is_backed_up_outside_skills(tmp_path: Path) -> None:
    _old_skill(tmp_path)
    bin_link = tmp_path / ".local" / "bin" / "leetcode"
    bin_link.parent.mkdir(parents=True)
    bin_link.symlink_to(tmp_path / ".claude" / "skills" / "leetcode" / "leetcode")
    proc = _run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    backups = list((tmp_path / ".claude" / "backups").glob("skill-leetcode-*"))
    assert len(backups) == 1
    assert (backups[0] / "leetcode_repl.py").is_file()
    assert sorted(p.name for p in (tmp_path / ".claude" / "skills").iterdir()) == [
        "leetcode"
    ]
    assert (tmp_path / ".claude" / "skills" / "leetcode").resolve() == COACH
    assert bin_link.resolve() == COACH / "leetcode"


def test_existing_symlink_is_repointed(tmp_path: Path) -> None:
    skills = tmp_path / ".claude" / "skills"
    skills.mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (skills / "leetcode").symlink_to(elsewhere)
    assert _run(tmp_path).returncode == 0
    assert (skills / "leetcode").resolve() == COACH
    assert list(elsewhere.iterdir()) == []


def test_unknown_directory_is_refused(tmp_path: Path) -> None:
    other = tmp_path / ".claude" / "skills" / "leetcode"
    other.mkdir(parents=True)
    (other / "notes.txt").write_text("mine", encoding="utf-8")
    proc = _run(tmp_path)
    assert proc.returncode == 1
    assert "not replacing it" in proc.stderr
    assert (other / "notes.txt").is_file()
    assert not other.is_symlink()


def test_regular_file_at_the_command_is_refused(tmp_path: Path) -> None:
    bin_file = tmp_path / ".local" / "bin" / "leetcode"
    bin_file.parent.mkdir(parents=True)
    bin_file.write_text("#!/bin/sh\n", encoding="utf-8")
    proc = _run(tmp_path)
    assert proc.returncode == 1
    assert not bin_file.is_symlink()
