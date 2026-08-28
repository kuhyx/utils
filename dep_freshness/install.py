"""Install the three gate pieces into a repo, from one set of templates.

The gate ships as three hand-replicated files per repo -- a delegate script, a
pre-commit hook entry and a CI workflow -- and hand-replication is exactly how
the 250-line cap ended up with four different hook ids, two of them
independent reimplementations rather than delegates. Sixteen more repos of
copy-paste would repeat that, so the copy is a script and the templates have
one home.

Idempotent by design: running it twice changes nothing the second time, and
`plan()` reports what a run WOULD do without touching the repo.
"""

from __future__ import annotations

from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent / "templates"
DELEGATE = Path("scripts/check_dependency_freshness.sh")
WORKFLOW = Path(".github/workflows/dependency-freshness.yml")
PRECOMMIT = Path(".pre-commit-config.yaml")
HOOK_ID = "dependency-freshness"

EMPTY_PRECOMMIT = "repos:\n  - repo: local\n    hooks:\n"


def _template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def _needs_delegate(repo: Path) -> bool:
    target = repo / DELEGATE
    return not target.is_file() or target.read_text(encoding="utf-8") != _template(
        "delegate.sh"
    )


def _needs_workflow(repo: Path) -> bool:
    target = repo / WORKFLOW
    return not target.is_file() or target.read_text(encoding="utf-8") != _template(
        "workflow.yml"
    )


def _needs_hook(repo: Path) -> bool:
    target = repo / PRECOMMIT
    if not target.is_file():
        return True
    return f"id: {HOOK_ID}" not in target.read_text(encoding="utf-8")


def _write_hook(repo: Path) -> None:
    """Append the hook block to the repo's `local` hooks list.

    Appending rather than parsing-and-re-emitting is deliberate: every one of
    these configs carries comments explaining why a hook exists, and a YAML
    round-trip through the standard library drops all of them.
    """
    target = repo / PRECOMMIT
    body = target.read_text(encoding="utf-8") if target.is_file() else EMPTY_PRECOMMIT
    if not body.endswith("\n"):
        body += "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{body}\n{_template('precommit-hook.yaml')}", encoding="utf-8")


def plan(repo: Path) -> list[str]:
    """Which pieces are missing or have drifted from the template."""
    todo = []
    if _needs_delegate(repo):
        todo.append(str(DELEGATE))
    if _needs_workflow(repo):
        todo.append(str(WORKFLOW))
    if _needs_hook(repo):
        todo.append(f"{PRECOMMIT} ({HOOK_ID} hook)")
    return todo


def install(repo: Path) -> list[str]:
    """Write every missing or drifted piece. Returns what changed."""
    done = []
    if _needs_delegate(repo):
        target = repo / DELEGATE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_template("delegate.sh"), encoding="utf-8")
        target.chmod(0o755)
        done.append(str(DELEGATE))
    if _needs_workflow(repo):
        target = repo / WORKFLOW
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_template("workflow.yml"), encoding="utf-8")
        done.append(str(WORKFLOW))
    if _needs_hook(repo):
        _write_hook(repo)
        done.append(f"{PRECOMMIT} ({HOOK_ID} hook)")
    return done


def write_fvmrc(repo: Path, version: str) -> bool:
    """Pin the Flutter SDK. Returns True if the file changed.

    Only for repos that actually hold a pubspec.yaml -- an .fvmrc in a Python
    repo is a declaration about a toolchain nothing there builds with, and the
    gate would then check a version that cannot go stale in any useful sense.
    """
    if not any(repo.rglob("pubspec.yaml")):
        return False
    target = repo / ".fvmrc"
    body = '{\n  "flutter": "%s"\n}\n' % version
    if target.is_file() and target.read_text(encoding="utf-8") == body:
        return False
    target.write_text(body, encoding="utf-8")
    return True
