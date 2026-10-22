"""Web-build detection and the `[agent_ready]` table of repo-contract.toml."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from repo_contract import web

from .conftest import write

PKG = '{"scripts": {"build": "tsc -b && vite build"}}'


def vite_repo(root: Path, lock: str = "pnpm-lock.yaml") -> Path:
    """A minimal Vite site: package.json with a build script + vite config."""
    write(root, "package.json", PKG)
    write(root, "vite.config.ts", "export default {}\n")
    write(root, "index.html", "<!doctype html>\n")
    if lock:
        write(root, lock, "")
    return root


def config(root: Path, body: str) -> None:
    write(root, web.CONFIG.as_posix(), body)


def test_detects_vite_with_pnpm(tmp_path: Path) -> None:
    got = web.detect(vite_repo(tmp_path))
    assert got == web.AgentReady(
        mode="dist",
        target="dist",
        build="pnpm run build",
        install="pnpm install --frozen-lockfile",
    )


@pytest.mark.parametrize(
    ("lock", "install"),
    [
        ("yarn.lock", "yarn install --frozen-lockfile"),
        ("package-lock.json", "npm ci"),
        ("", "npm install"),
    ],
)
def test_install_command_follows_lockfile(
    tmp_path: Path, lock: str, install: str
) -> None:
    got = web.detect(vite_repo(tmp_path, lock))
    assert got is not None and got.install == install


def test_out_dir_read_from_vite_config(tmp_path: Path) -> None:
    vite_repo(tmp_path)
    write(tmp_path, "vite.config.ts", "export default { build: { outDir: './site' } }")
    got = web.detect(tmp_path)
    assert got is not None and got.target == "site"


def test_index_html_alone_is_enough(tmp_path: Path) -> None:
    write(tmp_path, "package.json", PKG)
    write(tmp_path, "index.html", "<!doctype html>\n")
    assert web.detect(tmp_path) is not None


def test_astro_config_is_enough(tmp_path: Path) -> None:
    write(tmp_path, "package.json", PKG)
    write(tmp_path, "astro.config.mjs", "export default {}\n")
    assert web.detect(tmp_path) is not None


@pytest.mark.parametrize(
    "files",
    [
        {"package.json": PKG},  # node, no web entry point: a library/CLI
        {"package.json": '{"scripts": {"dev": "vite"}}', "index.html": "x"},
        {"package.json": "not json", "index.html": "x"},
        {"index.html": "x"},  # no package.json at all
        {"pyproject.toml": "[project]\nname='x'\n"},
    ],
)
def test_conservative_detection(tmp_path: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        write(tmp_path, rel, body)
    assert web.detect(tmp_path) is None


def test_load_absent_file_or_table(tmp_path: Path) -> None:
    assert web.load(tmp_path) is None
    config(tmp_path, "[other]\nx = 1\n")
    assert web.load(tmp_path) is None


def test_load_dist_url_skip(tmp_path: Path) -> None:
    config(tmp_path, '[agent_ready]\ndist = "./out/"\nbuild = "make"\nact = true\n')
    assert web.load(tmp_path) == web.AgentReady("dist", "out", "make", None, True)
    config(tmp_path, '[agent_ready]\nurl = "https://x.example"\n')
    assert web.load(tmp_path) == web.AgentReady("url", "https://x.example")
    config(tmp_path, '[agent_ready]\nskip = "auth-gated service"\n')
    assert web.load(tmp_path) == web.AgentReady("skip", "auth-gated service")


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ("[agent_ready\n", "not valid TOML"),
        ("agent_ready = 1\n", "must be a table"),
        ("[agent_ready]\n", "exactly one of"),
        ('[agent_ready]\ndist = "d"\nurl = "https://x"\n', "exactly one of"),
        ('[agent_ready]\ndist = ""\n', "non-empty string"),
        ("[agent_ready]\nskip = 3\n", "non-empty string"),
        ('[agent_ready]\nurl = "ftp://x"\n', "http"),
        ('[agent_ready]\ndist = "/abs"\n', "relative"),
        ('[agent_ready]\ndist = "../up"\n', "relative"),
        ('[agent_ready]\nurl = "https://x"\nbuild = "b"\n', "only apply to dist"),
        ('[agent_ready]\ndist = "d"\nbuild = 1\n', "'build' must be a string"),
        ('[agent_ready]\ndist = "d"\nact = "yes"\n', "'act' must be true or false"),
        ('[agent_ready]\ndist = "d"\nbogus = 1\n', "unknown key"),
    ],
)
def test_load_rejects_bad_config(tmp_path: Path, body: str, match: str) -> None:
    config(tmp_path, body)
    with pytest.raises(web.ConfigError, match=match):
        web.load(tmp_path)


def test_render_round_trips(tmp_path: Path) -> None:
    cfg = web.AgentReady("dist", "dist", 'pnpm run "build"', "pnpm i", True)
    config(tmp_path, web.render(cfg))
    assert web.load(tmp_path) == cfg
    config(tmp_path, web.render(web.AgentReady("url", "https://x.example")))
    assert web.load(tmp_path) == web.AgentReady("url", "https://x.example")


def test_problems_flag_unconfigured_web_repo(tmp_path: Path) -> None:
    vite_repo(tmp_path)
    assert any("web build detected" in p for p in web.problems(tmp_path))


def test_problems_skip_and_non_web_pass(tmp_path: Path) -> None:
    assert web.problems(tmp_path) == []
    vite_repo(tmp_path)
    config(tmp_path, '[agent_ready]\nskip = "self-hosted app"\n')
    assert web.problems(tmp_path) == []


def test_problems_bad_config(tmp_path: Path) -> None:
    config(tmp_path, "[agent_ready]\n")
    assert web.problems(tmp_path)[0].startswith("repo-contract.toml:")


def test_problems_configured_without_gate_pieces(tmp_path: Path) -> None:
    config(tmp_path, '[agent_ready]\ndist = "dist"\n')
    found = web.problems(tmp_path)
    assert any("agent-ready hook" in p for p in found)
    assert any("scripts/check_agent_ready.sh" in p for p in found)
    write(tmp_path, "scripts/check_agent_ready.sh")
    write(tmp_path, ".pre-commit-config.yaml", "      - id: agent-ready\n")
    assert web.problems(tmp_path) == []


def test_files_filter_default_and_override(tmp_path: Path) -> None:
    assert web.hook_files(web.AgentReady("dist", "dist")) == web.DEFAULT_FILES
    config(tmp_path, '[agent_ready]\ndist = "d"\nfiles = "^(app/|site\\\\.toml$)"\n')
    cfg = web.load(tmp_path)
    assert cfg is not None and web.hook_files(cfg) == r"^(app/|site\.toml$)"
    config(tmp_path, web.render(cfg))
    assert web.load(tmp_path) == cfg


@pytest.mark.parametrize(
    "path",
    [
        "src/main.tsx",
        "public/robots.txt",
        "index.html",
        "vite.config.ts",
        "astro.config.mjs",
        "package.json",
        "pnpm-lock.yaml",
        "package-lock.json",
        "yarn.lock",
        "repo-contract.toml",
    ],
)
def test_default_filter_matches_web_files(path: str) -> None:
    assert re.search(web.DEFAULT_FILES, path)


@pytest.mark.parametrize("path", ["README.md", "tests/a.test.ts", "docs/src/x"])
def test_default_filter_skips_the_rest(path: str) -> None:
    assert not re.search(web.DEFAULT_FILES, path)


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ('[agent_ready]\ndist = "d"\nfiles = "("\n', "not a valid regex"),
        ('[agent_ready]\ndist = "d"\nfiles = 1\n', "'files' must be a string"),
    ],
)
def test_bad_files_filter(tmp_path: Path, body: str, match: str) -> None:
    config(tmp_path, body)
    with pytest.raises(web.ConfigError, match=match):
        web.load(tmp_path)
