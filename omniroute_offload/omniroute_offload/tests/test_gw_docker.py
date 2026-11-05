from __future__ import annotations

import gzip
import io
import subprocess
import urllib.request
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Self

import pytest

from omniroute_offload import _gw_config as gwc
from omniroute_offload import _gw_docker as dock

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def blocked(*_args: Any, **_kwargs: Any) -> Any:
        msg = "real process/network access is blocked in tests"
        raise AssertionError(msg)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(subprocess, "run", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(urllib.request, "build_opener", blocked)


@pytest.fixture
def cfg(tmp_path: Path) -> gwc.Config:
    return gwc.Config.from_env({"HOME": str(tmp_path), "OMNIROUTE_PORT": "20555"})


class Runner:
    """Fake subprocess.run: records argv, replays queued completed processes."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.kwargs: list[dict[str, Any]] = []
        self.results: list[Any] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> Any:
        self.calls.append(argv)
        self.kwargs.append(kwargs)
        if self.results:
            return self.results.pop(0)
        return SimpleNamespace(returncode=0, stdout="", stderr="")


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch) -> Runner:
    fake = Runner()
    monkeypatch.setattr(subprocess, "run", fake)
    return fake


class FakePopen:
    def __init__(self, data: bytes = b"", rc: int = 0, err: bytes | None = b"") -> None:
        self.stdout = io.BytesIO(data)
        self.stderr = None if err is None else io.BytesIO(err)
        self._rc = rc

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def wait(self) -> int:
        return self._rc


def test_docker_returns_stripped_stdout(run: Runner) -> None:
    run.results = [SimpleNamespace(returncode=0, stdout=" out\n", stderr="")]
    assert dock.docker("ps", timeout=7) == "out"
    assert run.calls == [["docker", "ps"]]
    assert run.kwargs[0]["timeout"] == 7


def test_docker_failure_raises_with_stderr(run: Runner) -> None:
    run.results = [SimpleNamespace(returncode=1, stdout="", stderr=" no such \n")]
    with pytest.raises(dock.DockerError, match="docker inspect failed: no such"):
        dock.docker("inspect", "x")


def test_status_running_and_missing(cfg: gwc.Config, run: Runner) -> None:
    run.results = [
        SimpleNamespace(returncode=0, stdout="running\n", stderr=""),
        SimpleNamespace(returncode=1, stdout="", stderr="Error: No such object"),
    ]
    assert dock.status(cfg) == "running"
    assert run.calls[0][:2] == ["docker", "inspect"]
    assert run.calls[0][-1] == cfg.name
    assert dock.status(cfg) is None


def test_recreate_removes_then_runs_on_image_volume_port(
    cfg: gwc.Config, run: Runner
) -> None:
    dock.recreate(cfg, "repo:1.2.3-web", "pw")
    assert run.calls[0] == ["docker", "rm", "-f", cfg.name]
    args = run.calls[1]
    assert args[:3] == ["docker", "run", "-d"]
    assert args[-1] == "repo:1.2.3-web"
    assert "INITIAL_PASSWORD=pw" in args
    assert "PORT=20555" in args
    assert f"{cfg.volume}:/app/data" in args
    assert args[args.index("--stop-timeout") + 1] == str(dock.STOP_TIMEOUT_S)


def test_recreate_propagates_run_failure(cfg: gwc.Config, run: Runner) -> None:
    run.results = [
        SimpleNamespace(returncode=1, stdout="", stderr=""),
        SimpleNamespace(returncode=125, stdout="", stderr="bad image"),
    ]
    with pytest.raises(dock.DockerError, match="bad image"):
        dock.recreate(cfg, "img", "pw")


def test_restart_and_pull(cfg: gwc.Config, run: Runner) -> None:
    dock.restart(cfg)
    dock.pull("repo:2.0.0-web")
    assert run.calls[0] == ["docker", "restart", "-t", "40", cfg.name]
    assert run.calls[1] == ["docker", "pull", "-q", "repo:2.0.0-web"]
    assert run.kwargs[1]["timeout"] == 900


class Docker:
    """Records `docker(...)` calls made by backup()."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str, timeout: float = 120) -> str:
        self.calls.append(args)
        return ""


@pytest.fixture
def fake_docker(monkeypatch: pytest.MonkeyPatch) -> Docker:
    fake = Docker()
    monkeypatch.setattr(dock, "docker", fake)
    return fake


def test_backup_writes_0600_gzip_stops_then_starts(
    cfg: gwc.Config, fake_docker: Docker, monkeypatch: pytest.MonkeyPatch
) -> None:
    popen_args: list[list[str]] = []

    def popen(argv: list[str], **_kw: Any) -> FakePopen:
        popen_args.append(argv)
        return FakePopen(b"TARBYTES")

    monkeypatch.setattr(subprocess, "Popen", popen)
    dest = dock.backup(cfg, "3.8.52-web")
    assert dest.parent == cfg.backup_dir
    assert dest.name.endswith("-3.8.52-web.tar.gz")
    assert dest.stat().st_mode & 0o777 == 0o600
    assert cfg.backup_dir.stat().st_mode & 0o777 == 0o700
    assert gzip.decompress(dest.read_bytes()) == b"TARBYTES"
    assert popen_args == [["docker", "cp", f"{cfg.name}:/app/data", "-"]]
    assert [c[0] for c in fake_docker.calls] == ["stop", "start"]


def test_backup_prunes_to_newest_four(
    cfg: gwc.Config, fake_docker: Docker, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg.backup_dir.mkdir(parents=True)
    old = [cfg.backup_dir / f"2000010{i}-000000-old.tar.gz" for i in range(1, 6)]
    for path in old:
        path.write_bytes(b"x")
    (cfg.backup_dir / "notes.txt").write_text("keep")
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: FakePopen(b"d"))
    dest = dock.backup(cfg, "new")
    left = sorted(p.name for p in cfg.backup_dir.glob("*.tar.gz"))
    assert len(left) == dock.KEEP_BACKUPS
    assert left == [*(p.name for p in old[2:]), dest.name]
    assert (cfg.backup_dir / "notes.txt").exists()


def test_failed_copy_removes_partial_and_still_restarts(
    cfg: gwc.Config, fake_docker: Docker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        subprocess, "Popen", lambda *_a, **_k: FakePopen(b"half", 1, b" cp boom\n")
    )
    with pytest.raises(dock.DockerError, match="docker cp failed: cp boom"):
        dock.backup(cfg, "x")
    assert list(cfg.backup_dir.glob("*.tar.gz")) == []
    assert [c[0] for c in fake_docker.calls] == ["stop", "start"]


def test_copy_out_without_stderr_pipe_succeeds(
    cfg: gwc.Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: FakePopen(b"d", 0, None))
    dest = tmp_path / "out.tar.gz"
    dock._copy_out(cfg, dest)
    assert gzip.decompress(dest.read_bytes()) == b"d"
    assert dest.stat().st_mode & 0o777 == 0o600


def test_restore_pipes_archive_into_helper_container(
    cfg: gwc.Config, run: Runner, tmp_path: Path
) -> None:
    archive = tmp_path / "a.tar.gz"
    archive.write_bytes(b"zz")
    dock.restore(cfg, "repo:1.0.0-web", archive)
    argv = run.calls[0]
    assert argv[:2] == ["docker", "run"]
    assert f"{cfg.volume}:/app/data" in argv
    assert "repo:1.0.0-web" in argv
    assert "stdin" in run.kwargs[0]


def test_restore_failure_raises(cfg: gwc.Config, run: Runner, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar.gz"
    archive.write_bytes(b"zz")
    run.results = [SimpleNamespace(returncode=2, stdout=b"", stderr=b" tar bad\n")]
    with pytest.raises(dock.DockerError, match="restore failed: tar bad"):
        dock.restore(cfg, "img", archive)
