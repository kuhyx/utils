# Copyright (c) 2026 Krzysztof Rudnicki
"""Starting external programs: path lookup, nice wrapper, spawn with log, env and detach."""

import os
from pathlib import Path
import shutil
import sys

import pytest

from game_recording import procs


def test_program_is_the_full_path_when_installed() -> None:
    found = shutil.which("sh")
    assert found is not None
    assert procs.program("sh") == found


def test_program_keeps_the_bare_name_when_missing() -> None:
    assert procs.program("no-such-program-xyz") == "no-such-program-xyz"


def test_niced_prefixes_the_resolved_nice() -> None:
    argv = procs.niced("7", ["ffmpeg", "-i", "x"])
    assert argv[1:] == ["-n", "7", "ffmpeg", "-i", "x"]
    assert Path(argv[0]).name == "nice"
    assert Path(argv[0]).is_absolute()


def test_spawn_runs_the_child_without_a_log() -> None:
    proc = procs.spawn([sys.executable, "-c", "pass"])
    assert proc.wait(timeout=20) == 0


def test_spawn_sends_output_to_the_log(tmp_path: Path) -> None:
    out = tmp_path / "out.log"
    with out.open("wb") as log:
        proc = procs.spawn([sys.executable, "-c", "import sys; print('o'); print('e', file=sys.stderr)"], log=log)
        assert proc.wait(timeout=20) == 0
    assert sorted(out.read_text().split()) == ["e", "o"]


def test_spawn_passes_the_given_env(tmp_path: Path) -> None:
    out = tmp_path / "env.log"
    code = "import os; print(os.environ['SPAWN_PROBE'], 'PATH' in os.environ)"
    with out.open("wb") as log:
        proc = procs.spawn([sys.executable, "-c", code], env={"SPAWN_PROBE": "yes"}, log=log)
        assert proc.wait(timeout=20) == 0
    assert out.read_text().split() == ["yes", "False"]


@pytest.mark.parametrize("detach", [False, True])
def test_spawn_detach_gives_the_child_its_own_session(tmp_path: Path, *, detach: bool) -> None:
    out = tmp_path / "sid.log"
    with out.open("wb") as log:
        proc = procs.spawn(
            [sys.executable, "-c", "import os; print(os.getsid(0), os.getpid())"], log=log, detach=detach
        )
        assert proc.wait(timeout=20) == 0
    sid, pid = (int(x) for x in out.read_text().split())
    assert (sid == pid) is detach
    assert (sid == os.getsid(0)) is (not detach)
