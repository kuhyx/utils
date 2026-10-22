"""Gate: the repo's website passes the shared AgentReady checker.

Usage: agent_ready_gate.py [--repo PATH] [--strict] [--install]

Reads `[agent_ready]` from repo-contract.toml (see web.py). dist mode runs the
`build` command in a throwaway copy of the tree (never the live dist), then `agent_ready/check.sh dist <dir>`; url mode runs
`check.sh url <url>`. `--install` runs `install` first (CI: fresh checkout).

Exit: 0 pass / no site / skip, 1 FAIL (checker, build or missing config),
2 malformed config, 3 undeterminable (url mode, only with --strict).

Without --strict an unreachable site degrades to a pass with a banner, like
dependency-freshness: `--no-verify` is banned, so an offline commit must still
go through, and CI (always online, always --strict) is the authority.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - plain-script import path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repo_contract.isolate import populate
from repo_contract.web import CONFIG, TABLE, AgentReady, ConfigError, detect, load

CHECKER = Path(__file__).resolve().parents[1] / "agent_ready" / "check.sh"
EXIT_OK, EXIT_FAIL, EXIT_CONFIG, EXIT_UNDETERMINABLE = 0, 1, 2, 3
TAIL = 40


def _run_step(repo: Path, label: str, command: str) -> bool:
    """Run a build/install command quietly; show its tail only on failure."""
    done = subprocess.run(
        ["bash", "-c", command],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode == 0:
        return True
    tail = (done.stdout + done.stderr).splitlines()[-TAIL:]
    print("\n".join(tail), file=sys.stderr)
    print(
        f"agent-ready: {label} failed (exit {done.returncode}): {command}",
        file=sys.stderr,
    )
    return False


def _run_checker(cfg: AgentReady, args: list[str], *, strict: bool) -> int:
    """Run the shared checker on `args` (mode + target); degrade exit 3 locally."""
    argv = [str(CHECKER), *args, *(["--act"] if cfg.act else [])]
    code = subprocess.run(["bash", *argv], check=False).returncode
    if code == EXIT_UNDETERMINABLE and not strict:
        print(
            f"agent-ready: DEGRADED: {cfg.target} unreachable, passing locally; "
            "CI (--strict) is the authority",
            file=sys.stderr,
        )
        return EXIT_OK
    return code


def _check(repo: Path, cfg: AgentReady, *, strict: bool, install: bool) -> int:
    """Build if configured, then run the shared checker; returns the exit code.

    The build runs in a throwaway copy (isolate.py): the live `dist` may be
    bind-mounted into a serving container, and a gate must never empty it.
    """
    if cfg.mode == "url":
        return _run_checker(cfg, ["url", cfg.target], strict=strict)
    if install and cfg.install and not _run_step(repo, "install", cfg.install):
        return EXIT_FAIL
    if not cfg.build:
        return _run_checker(cfg, ["dist", str(repo / cfg.target)], strict=strict)
    with tempfile.TemporaryDirectory(prefix="agent-ready-") as tmp:
        copy = Path(tmp) / repo.name
        copy.mkdir()
        populate(repo, copy)
        if not _run_step(copy, "build", cfg.build):
            return EXIT_FAIL
        return _run_checker(cfg, ["dist", str(copy / cfg.target)], strict=strict)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--strict", action="store_true", help="CI: offline fails")
    parser.add_argument("--install", action="store_true", help="run `install` first")
    args = parser.parse_args(argv)
    repo = args.repo.expanduser().resolve()
    try:
        cfg = load(repo)
    except ConfigError as exc:
        print(f"agent-ready: {CONFIG}: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if cfg is None:
        if detect(repo) is None:
            print("agent-ready: no website in this repo")
            return EXIT_OK
        print(
            f"agent-ready: web build detected but {CONFIG} has no [{TABLE}]; run "
            "~/src/utils/scripts/install_repo_contract_gate.sh",
            file=sys.stderr,
        )
        return EXIT_FAIL
    if cfg.mode == "skip":
        print(f"agent-ready: skipped: {cfg.target}")
        return EXIT_OK
    if os.environ.get("GITHUB_ACTIONS") and not args.strict:
        # A repo's generic pre-commit workflow has no node toolchain or deps;
        # the dedicated agent-ready workflow builds and checks with --strict.
        print("agent-ready: CI pre-commit run; the agent-ready workflow enforces it")
        return EXIT_OK
    return _check(repo, cfg, strict=args.strict, install=args.install)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
