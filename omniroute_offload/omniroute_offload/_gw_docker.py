"""Docker operations on one gateway: recreate, restart, backup, restore."""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import time
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pathlib import Path
    from typing import IO

    from omniroute_offload._gw_config import Config

STOP_TIMEOUT_S = 40
KEEP_BACKUPS = 4


class DockerError(RuntimeError):
    """A docker command failed."""


def docker(*args: str, timeout: float = 120) -> str:
    """Run docker, return stdout; raise DockerError with stderr on failure."""
    proc = subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=False, timeout=timeout
    )
    if proc.returncode:
        msg = f"docker {args[0]} failed: {proc.stderr.strip()}"
        raise DockerError(msg)
    return proc.stdout.strip()


def status(cfg: Config) -> str | None:
    """Return 'running', 'exited', ... or None when the container is missing."""
    try:
        return docker("inspect", "-f", "{{.State.Status}}", cfg.name)
    except DockerError:
        return None


def recreate(cfg: Config, image: str, password: str) -> None:
    """Replace the container with one on `image`, same volume and port."""
    subprocess.run(
        ["docker", "rm", "-f", cfg.name], capture_output=True, check=False, timeout=90
    )
    docker(
        "run", "-d", "--name", cfg.name,
        "--restart", "unless-stopped", "--stop-timeout", str(STOP_TIMEOUT_S),
        "-e", "OMNIROUTE_MEMORY_MB=8192", "--memory=10g",
        "-e", f"INITIAL_PASSWORD={password}",
        "--network", "host", "-e", "OMNIROUTE_HOSTNAME=127.0.0.1",
        "-e", f"PORT={cfg.port}",
        "-v", f"{cfg.volume}:/app/data", image,
    )  # fmt: skip


def restart(cfg: Config) -> None:
    """Docker restart (starts it too when it is stopped)."""
    docker("restart", "-t", str(STOP_TIMEOUT_S), cfg.name)


def pull(image: str) -> None:
    """Fetch an image."""
    docker("pull", "-q", image, timeout=900)


def backup(cfg: Config, label: str) -> Path:
    """Stop, tar /app/data (gzip, 0600), start again; keep the newest few."""
    cfg.backup_dir.mkdir(parents=True, exist_ok=True)
    cfg.backup_dir.chmod(0o700)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = cfg.backup_dir / f"{stamp}-{label}.tar.gz"
    docker("stop", "-t", str(STOP_TIMEOUT_S), cfg.name)
    try:
        _copy_out(cfg, dest)
    finally:
        docker("start", cfg.name)
    _prune(cfg.backup_dir)
    return dest


def _copy_out(cfg: Config, dest: Path) -> None:
    # The tar holds API keys and server.env: create it 0600 before writing.
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with (
        os.fdopen(fd, "wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb") as out,
        subprocess.Popen(
            ["docker", "cp", f"{cfg.name}:/app/data", "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc,
    ):
        shutil.copyfileobj(cast("IO[bytes]", proc.stdout), out)
        err = proc.stderr.read().decode() if proc.stderr else ""
        rc = proc.wait()
    if rc:
        dest.unlink(missing_ok=True)
        msg = f"docker cp failed: {err.strip()}"
        raise DockerError(msg)


def _prune(directory: Path) -> None:
    for old in sorted(directory.glob("*.tar.gz"))[:-KEEP_BACKUPS]:
        old.unlink()


def restore(cfg: Config, image: str, archive: Path) -> None:
    """Wipe the volume and unpack `archive` into it (container must be stopped)."""
    script = "find /app/data -mindepth 1 -delete && tar -xz -C /app"
    with archive.open("rb") as src:
        proc = subprocess.run(
            [
                "docker", "run", "--rm", "-i", "--user", "0",
                "-v", f"{cfg.volume}:/app/data", "--entrypoint", "sh", image,
                "-c", script,
            ],
            stdin=src, capture_output=True, check=False, timeout=300,
        )  # fmt: skip
    if proc.returncode:
        msg = f"restore failed: {proc.stderr.decode().strip()}"
        raise DockerError(msg)
