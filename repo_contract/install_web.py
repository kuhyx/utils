"""The AgentReady half of the installer: a website gets the agent-ready gate.

Why it rides on install_repo_contract_gate.sh rather than a separate script:
that installer is already the one step every new repo gets after `git init`,
so a new Vite site cannot come out of scaffolding without the gate. Pieces,
mirroring the repo-contract and dependency-freshness gates: the
`[agent_ready]` table in repo-contract.toml (proposed from detection, never
overwritten), the scripts/check_agent_ready.sh delegate, the pre-commit hook
and the agent-ready CI workflow (skipped when the repo has no Actions).
"""

from __future__ import annotations

from pathlib import Path

from dep_freshness.install import NO_WORKFLOW_MARKER
from repo_contract.precommit import (
    PRECOMMIT,
    hook_line,
    needs_hook,
    set_hook_line,
    write_hook,
)
from repo_contract.web import (
    CONFIG,
    HOOK_ID,
    SHIM,
    TABLE,
    WORKFLOW,
    AgentReady,
    ConfigError,
    detect,
    hook_files,
    load,
    render,
)

TEMPLATES = Path(__file__).resolve().parent / "templates"
HEADER = (
    "# Repo-contract settings, read by ~/src/utils/repo_contract.\n"
    "# [agent_ready]: this repo is a website and must pass the AgentReady\n"
    "# checker (~/src/utils/agent_ready). See repo_contract/web.py for keys.\n\n"
)
CONFIG_PIECE = f"{CONFIG} ([{TABLE}])"
HOOK_PIECE = f"{PRECOMMIT} ({HOOK_ID} hook)"


def _template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def _drifted(repo: Path, rel: Path, template: str) -> bool:
    target = repo / rel
    return not target.is_file() or target.read_text(encoding="utf-8") != _template(
        template
    )


def _files_line(cfg: AgentReady) -> str:
    """The hook's `files:` line: the regex as a single-quoted YAML scalar."""
    return "        files: '" + hook_files(cfg).replace("'", "''") + "'"


def _settings(repo: Path) -> tuple[AgentReady | None, bool]:
    """(settings to gate with, whether the config must be written)."""
    try:
        declared = load(repo)
    except ConfigError:
        return None, False  # check.py reports it; never guess over a typo
    if declared is not None:
        return (None if declared.mode == "skip" else declared), False
    proposed = detect(repo)
    return proposed, proposed is not None


def _pieces(repo: Path) -> tuple[AgentReady | None, list[str]]:
    cfg, write_config = _settings(repo)
    if cfg is None:
        return None, []
    todo = [CONFIG_PIECE] if write_config else []
    if _drifted(repo, SHIM, "check_agent_ready.shim.sh"):
        todo.append(str(SHIM))
    if not (repo / NO_WORKFLOW_MARKER).exists() and _drifted(
        repo, WORKFLOW, "agent-ready.yml"
    ):
        todo.append(str(WORKFLOW))
    if needs_hook(repo, HOOK_ID) or hook_line(repo, HOOK_ID, "files") != _files_line(
        cfg
    ):
        todo.append(HOOK_PIECE)
    return cfg, todo


def plan_web(repo: Path) -> list[str]:
    """Which AgentReady gate pieces are missing or drifted."""
    return _pieces(repo)[1]


def _write_config(repo: Path, cfg: AgentReady) -> None:
    target = repo / CONFIG
    if target.is_file():
        body = target.read_text(encoding="utf-8")
        body = (body if body.endswith("\n") else body + "\n") + "\n"
    else:
        body = HEADER
    target.write_text(body + render(cfg), encoding="utf-8")


def install_web(repo: Path) -> list[str]:
    """Write every missing or drifted AgentReady gate piece. Returns them."""
    cfg, todo = _pieces(repo)
    if cfg is not None and CONFIG_PIECE in todo:
        _write_config(repo, cfg)
    if str(SHIM) in todo:
        target = repo / SHIM
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_template("check_agent_ready.shim.sh"), encoding="utf-8")
        target.chmod(0o755)
    if str(WORKFLOW) in todo:
        target = repo / WORKFLOW
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_template("agent-ready.yml"), encoding="utf-8")
    if cfg is not None and HOOK_PIECE in todo:
        if needs_hook(repo, HOOK_ID):
            write_hook(repo, _template("agent-ready-hook.yaml"))
        set_hook_line(repo, HOOK_ID, "files", _files_line(cfg))
    return todo
