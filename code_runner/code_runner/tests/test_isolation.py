"""Escape attempts: each one runs hostile code in the real sandbox and must fail."""

from __future__ import annotations

from pathlib import Path
import socket
import subprocess
import time
from typing import Any, cast

import pytest

from code_runner import CaseResult, Example, Limits, run
from code_runner.tests.conftest import needs_node, needs_sandbox

pytestmark = needs_sandbox
STARTER = "def f(a):\n"
FAST = Limits(timeout_s=1.0)


def _one(code: str, lang: str = "python3", limits: Limits = FAST) -> CaseResult:
    starter = {"python3": STARTER, "javascript": "var f = function(a) {};"}[lang]
    return run(lang, code, starter, [Example(1, {"a": 0}, 1)], limits=limits)[0]


def _pgrep(pattern: str) -> int:
    done = subprocess.run(
        ["/usr/bin/pgrep", "-fc", pattern], capture_output=True, text=True, check=False
    )
    return int(done.stdout.strip() or 0)


def test_no_network_not_even_host_loopback() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(0)
        port = listener.getsockname()[1]
        code = (
            "import socket\n"
            "def f(a):\n"
            "    out = []\n"
            f"    for host, port in [('127.0.0.1', {port}), ('1.1.1.1', 53), ('::1', {port})]:\n"
            "        try:\n"
            "            socket.create_connection((host, port), timeout=1).close()\n"
            "            out.append('connected')\n"
            "        except OSError:\n"
            "            out.append('blocked')\n"
            "    return out\n"
        )
        result = _one(code)
        with pytest.raises(BlockingIOError):
            listener.accept()
    assert result.actual == ["blocked", "blocked", "blocked"]


@needs_node
def test_no_network_from_node() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        code = (
            "var f = function(a) {\n"
            "  const net = process.getBuiltinModule('node:net');\n"
            "  let seen = 'pending';\n"
            f"  const s = net.connect({port}, '127.0.0.1');\n"
            "  s.on('connect', () => { seen = 'connected'; });\n"
            "  s.on('error', () => {});\n"
            "  return seen;\n"
            "};"
        )
        result = _one(code, "javascript")
        listener.settimeout(0.2)
        with pytest.raises(TimeoutError):
            listener.accept()
    assert result.actual == "pending"


def test_writes_outside_scratch_never_reach_the_host(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    code = (
        "def f(a):\n"
        "    out = []\n"
        f"    for path in ['/usr/escape', '/etc/escape', '/escape', {str(marker)!r}]:\n"
        "        try:\n"
        "            open(path, 'w').write('x')\n"
        "            out.append('wrote')\n"
        "        except OSError:\n"
        "            out.append('denied')\n"
        "    return out\n"
    )
    result = _one(code)
    assert result.actual == ["denied", "denied", "denied", "denied"]
    assert not marker.exists()
    assert not Path("/usr/escape").exists()


def test_host_files_and_environment_are_invisible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("hunter2")
    monkeypatch.setenv("CODE_RUNNER_SECRET", "hunter2")
    code = (
        "import os\n"
        "def f(a):\n"
        f"    return [os.path.exists({str(secret)!r}), os.path.exists({str(Path.home())!r}),\n"
        "            'CODE_RUNNER_SECRET' in os.environ, sorted(os.environ), os.getpid() < 20,\n"
        "            os.path.exists('/proc/1/environ') and 'hunter2' in open('/proc/1/environ').read()]\n"
    )
    values = cast("list[Any]", _one(code).actual)
    exists, home, env_leak, names, own_pidns, proc_leak = values
    assert (exists, home, env_leak, own_pidns, proc_leak) == (
        False,
        False,
        False,
        True,
        False,
    )
    assert set(names) <= {"HOME", "LANG", "PATH", "PWD", "PYTHONIOENCODING"}


def test_symlink_in_scratch_cannot_exfiltrate_a_host_file(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("hunter2-secret-contents")
    code = (
        "import os\n"
        "def f(a):\n"
        f"    os.symlink({str(secret)!r}, '/work/result.json')\n"
        "    return 7\n"
    )
    result = _one(code)
    assert "hunter2" not in repr(result)
    assert result.actual == 7  # the harness replaced the link, never followed it


def test_fork_bomb_is_contained_and_leaves_nothing_behind() -> None:
    before = _pgrep("python3 -I /work/harness.py")
    code = (
        "import os, subprocess\n"
        "def f(a):\n"
        "    subprocess.Popen(['sleep', '97'])\n"
        "    while True:\n"
        "        os.fork()\n"
    )
    started = time.monotonic()
    result = _one(code)
    assert time.monotonic() - started < 6
    assert result.ok is False
    assert result.error is not None
    assert result.error.startswith(("TimeLimitExceeded", "BlockingIOError"))
    time.sleep(0.3)
    assert _pgrep("python3 -I /work/harness.py") == before
    assert _pgrep("^sleep 97$") == 0


def test_memory_bomb_is_a_visible_error() -> None:
    result = _one("def f(a):\n    return len(bytearray(8 * 1024**3))\n")
    assert result.ok is False
    assert result.error is not None
    assert result.error.startswith("MemoryError")


@needs_node
def test_node_heap_bomb_is_a_visible_error() -> None:
    code = "var f = function(a) { const x = []; for (;;) x.push(new Array(1e6).fill(1)); };"
    result = _one(code, "javascript", Limits(timeout_s=5.0))
    assert result.ok is False
    assert result.error in {"MemoryLimitExceeded", "RangeError: Invalid array length"}


def test_output_flood_is_capped() -> None:
    code = "def f(a):\n    while True:\n        print('x' * 1000)\n"
    started = time.monotonic()
    result = _one(code)
    assert time.monotonic() - started < 6
    assert result.ok is False
    assert len(result.stdout) <= 64 * 1024


def test_disk_fill_is_capped_by_the_file_size_limit() -> None:
    code = (
        "def f(a):\n"
        "    with open('/work/big', 'wb') as fh:\n"
        "        while True:\n"
        "            fh.write(b'x' * 65536)\n"
    )
    result = _one(code)
    assert result.ok is False
    assert result.error is not None
    assert "OSError" in result.error


def test_timeout_kills_every_process_the_solution_started() -> None:
    code = (
        "import subprocess\n"
        "def f(a):\n"
        "    subprocess.Popen(['sleep', '97'])\n"
        "    while True:\n"
        "        pass\n"
    )
    result = _one(code)
    assert result.error == "TimeLimitExceeded"
    time.sleep(0.3)
    assert _pgrep("^sleep 97$") == 0
