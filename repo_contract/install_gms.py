"""The no-GMS-sign-in half of the installer: Flutter Android apps get the gate.

Why it rides on install_repo_contract_gate.sh: that installer is the one step
every new repo gets after `git init`, so a new Flutter app cannot come out of
scaffolding able to re-add google_sign_in (13 apps were migrated off it onto
utils/google_account_token in November 2026). Pieces: the
scripts/check_no_gms_signin.sh delegate and an always-run pre-commit hook.
Only repos with a pubspec.yaml next to an android/ dir (at the root or one
level down, e.g. tutor/app) get it; utils itself holds the real gate.
"""

from __future__ import annotations

from pathlib import Path

from repo_contract.precommit import PRECOMMIT, needs_hook, write_hook

TEMPLATES = Path(__file__).resolve().parent / "templates"
SHIM = Path("scripts/check_no_gms_signin.sh")
HOOK_ID = "no-gms-signin"
HOOK_PIECE = f"{PRECOMMIT} ({HOOK_ID} hook)"
SHIM_TEMPLATE = "check_no_gms_signin.shim.sh"


def _template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def is_flutter_android(repo: Path) -> bool:
    """A pubspec.yaml beside an android/ dir, at the root or one level down."""
    if (repo / "repo_contract" / "check.py").is_file():
        return False  # utils: SHIM is the real gate, never a delegate
    pubspecs = [repo / "pubspec.yaml", *repo.glob("*/pubspec.yaml")]
    return any(p.is_file() and (p.parent / "android").is_dir() for p in pubspecs)


def plan_gms(repo: Path) -> list[str]:
    """Which no-GMS-sign-in gate pieces are missing or drifted."""
    if not is_flutter_android(repo):
        return []
    todo = []
    shim = repo / SHIM
    if not shim.is_file() or shim.read_text(encoding="utf-8") != _template(
        SHIM_TEMPLATE
    ):
        todo.append(str(SHIM))
    if needs_hook(repo, HOOK_ID):
        todo.append(HOOK_PIECE)
    return todo


def install_gms(repo: Path) -> list[str]:
    """Write every missing or drifted no-GMS-sign-in piece. Returns them."""
    todo = plan_gms(repo)
    if str(SHIM) in todo:
        target = repo / SHIM
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_template(SHIM_TEMPLATE), encoding="utf-8")
        target.chmod(0o755)
    if HOOK_PIECE in todo:
        write_hook(repo, _template("no-gms-signin-hook.yaml"))
    return todo
