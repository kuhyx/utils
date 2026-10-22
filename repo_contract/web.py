"""Which repos are websites, and their `[agent_ready]` table in repo-contract.toml.

Every website kuhy owns must pass the AgentReady checker
(`~/src/utils/agent_ready`). A repo opts in, or is detected and proposed, with:

    [agent_ready]
    dist = "dist"                              # build output dir, or
    url = "https://site.example"               # live site (server-rendered), or
    skip = "self-hosted app behind auth"       # not a website: a reason, always
    build = "pnpm run build"                   # dist only, optional
    install = "pnpm install --frozen-lockfile" # dist only, CI runs it first
    act = true                                 # optional: also run act items
    files = "^(src/|public/)"                  # optional: pre-commit files regex

The pre-commit hook only builds when a web-relevant file is staged (DEFAULT_FILES
unless `files` overrides it); CI rebuilds and checks on every push regardless.

TOML because it parses with the stdlib: the CI runner of the repo-contract
workflow installs nothing, and agent_ready itself is stdlib-only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import tomllib

from repo_contract.infer import _pm
from repo_contract.sources import package_scripts, read_text

CONFIG = Path("repo-contract.toml")
TABLE = "agent_ready"
SHIM = Path("scripts/check_agent_ready.sh")
WORKFLOW = Path(".github/workflows/agent-ready.yml")
HOOK_ID = "agent-ready"
MODES = ("dist", "url", "skip")
OPTIONAL = ("build", "install", "act", "files")
DEFAULT_FILES = (
    r"^(src/|public/|index\.html$|(vite|astro)\.config\.[cm]?[jt]s$"
    r"|package\.json$|pnpm-lock\.yaml$|package-lock\.json$|yarn\.lock$"
    r"|repo-contract\.toml$)"
)
_EXTS = ("js", "ts", "mjs", "mts", "cjs", "cts")
VITE = tuple(f"vite.config.{e}" for e in _EXTS)
ASTRO = tuple(f"astro.config.{e}" for e in _EXTS)
_OUT_DIR = re.compile(r"""outDir\s*:\s*['"]([^'"]+)['"]""")
INSTALL = {
    "pnpm": "pnpm install --frozen-lockfile",
    "yarn": "yarn install --frozen-lockfile",
}


class ConfigError(ValueError):
    """The `[agent_ready]` table exists but is malformed."""


@dataclass(frozen=True)
class AgentReady:
    """One repo's AgentReady gate settings."""

    mode: str
    target: str
    build: str | None = None
    install: str | None = None
    act: bool = False
    files: str | None = None


def _clean_dist(value: str) -> str:
    """`./out/` -> `out`; refuse paths that leave the repo."""
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ConfigError(f"dist must be a relative path inside the repo: {value!r}")
    return path.as_posix()


def _string(table: dict[str, object], key: str) -> str | None:
    value = table.get(key)
    if value is not None and not isinstance(value, str):
        raise ConfigError(f"'{key}' must be a string")
    return value


def _parse(table: dict[str, object]) -> AgentReady:
    unknown = sorted(set(table) - set(MODES) - set(OPTIONAL))
    if unknown:
        raise ConfigError(f"unknown key(s) in [{TABLE}]: {', '.join(unknown)}")
    modes = [m for m in MODES if m in table]
    if len(modes) != 1:
        raise ConfigError(f"[{TABLE}] needs exactly one of: {', '.join(MODES)}")
    mode, target = modes[0], table[modes[0]]
    if not isinstance(target, str) or not target.strip():
        raise ConfigError(f"'{mode}' must be a non-empty string")
    build, install = _string(table, "build"), _string(table, "install")
    if mode != "dist" and (build or install):
        raise ConfigError("'build'/'install' only apply to dist mode")
    if mode == "url" and not target.startswith(("http://", "https://")):
        raise ConfigError(f"url must be http(s)://: {target!r}")
    act = table.get("act", False)
    if not isinstance(act, bool):
        raise ConfigError("'act' must be true or false")
    if mode == "dist":
        target = _clean_dist(target)
    files = _string(table, "files")
    if files is not None:
        try:
            re.compile(files)
        except re.error as exc:
            raise ConfigError(f"'files' is not a valid regex: {exc}") from exc
    return AgentReady(mode, target, build, install, act, files)


def load(repo: Path) -> AgentReady | None:
    """The repo's `[agent_ready]` settings; None when not declared."""
    path = repo / CONFIG
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(read_text(path))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"not valid TOML: {exc}") from exc
    if TABLE not in data:
        return None
    if not isinstance(data[TABLE], dict):
        raise ConfigError(f"'{TABLE}' must be a table: [{TABLE}]")
    return _parse(data[TABLE])


def _install_command(repo: Path) -> str:
    pm = _pm(repo)
    if pm in INSTALL:
        return INSTALL[pm]
    return "npm ci" if (repo / "package-lock.json").is_file() else "npm install"


def detect(repo: Path) -> AgentReady | None:
    """Proposed settings for a node web build; None when not clearly a site.

    Conservative on purpose: package.json must carry a `build` script AND the
    repo must have a Vite/Astro config or a root index.html. Python and other
    server-rendered sites are opt-in (`url = ...`), never guessed.
    """
    if "build" not in package_scripts(repo):
        return None
    configs = [repo / n for n in (*VITE, *ASTRO) if (repo / n).is_file()]
    if not configs and not (repo / "index.html").is_file():
        return None
    out = next(
        (m.group(1) for c in configs if (m := _OUT_DIR.search(read_text(c)))), "dist"
    )
    return AgentReady(
        "dist", _clean_dist(out), f"{_pm(repo)} run build", _install_command(repo)
    )


def render(cfg: AgentReady) -> str:
    """The `[agent_ready]` TOML table for `cfg` (json strings are TOML strings)."""
    lines = [f"[{TABLE}]", f"{cfg.mode} = {json.dumps(cfg.target)}"]
    lines += [
        f"{key} = {json.dumps(value)}"
        for key, value in (("build", cfg.build), ("install", cfg.install))
        if value
    ]
    if cfg.act:
        lines.append("act = true")
    if cfg.files is not None:
        lines.append(f"files = {json.dumps(cfg.files)}")
    return "\n".join(lines) + "\n"


def hook_files(cfg: AgentReady) -> str:
    """The pre-commit `files:` regex for the agent-ready hook."""
    return DEFAULT_FILES if cfg.files is None else cfg.files


def has_hook(repo: Path) -> bool:
    """Whether the pre-commit config already runs the agent-ready hook."""
    return f"id: {HOOK_ID}" in read_text(repo / ".pre-commit-config.yaml")


def problems(repo: Path) -> list[str]:
    """Repo-contract violations about the AgentReady gate."""
    try:
        cfg = load(repo)
    except ConfigError as exc:
        return [f"{CONFIG}: {exc}"]
    fix = "run ~/src/utils/scripts/install_repo_contract_gate.sh"
    if cfg is None:
        if detect(repo) is None:
            return []
        return [
            (
                f"web build detected but {CONFIG} has no [{TABLE}] table: {fix}, "
                'or declare skip = "<why this is not a website>"'
            )
        ]
    if cfg.mode == "skip":
        return []
    out = []
    if not has_hook(repo):
        out.append(f"[{TABLE}] is set but no {HOOK_ID} hook in pre-commit: {fix}")
    if not (repo / SHIM).is_file():
        out.append(f"[{TABLE}] is set but {SHIM} is missing: {fix}")
    return out
