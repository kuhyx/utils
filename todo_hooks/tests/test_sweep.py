"""Tests for the nightly drift sweep."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todo_hooks import sweep
from todo_hooks.checkrun import CheckResult
from todo_hooks.client import McpToolError, McpUnavailable
from todo_hooks.tests._fakes import FakeClient, detail, line
from todo_hooks.trust import add_trusted

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todo_hooks.context import Context
    from todo_hooks.paths import Paths

A = "aaaaaaaa-0000-4000-8000-000000000001"
B = "bbbbbbbb-0000-4000-8000-000000000002"
C = "cccccccc-0000-4000-8000-000000000003"
D = "dddddddd-0000-4000-8000-000000000004"
E = "eeeeeeee-0000-4000-8000-000000000005"
F = "ffffffff-0000-4000-8000-000000000006"

Fixture = "tuple[Context, list[str], FakeClient]"


def _client(*tasks: tuple[str, str]) -> FakeClient:
    """`tasks` are (list line, detail) pairs."""
    details = {d.splitlines()[0].removeprefix("id: ")[:8]: d for _, d in tasks}
    return FakeClient(
        {
            "list_tasks": "\n".join(row for row, _ in tasks) or "no tasks match",
            "get_task": lambda args: details[args["id"]],
        }
    )


def _task(task_id: str, repo: str, title: str, **kw: object) -> tuple[str, str]:
    return (
        line(task_id, repo, f"# {title}"),
        detail(task_id, repo=repo, text=f"# {title}\n\nbody", **kw),  # type: ignore[arg-type]
    )


def _runner(results: dict[str, CheckResult]) -> Callable[..., CheckResult]:
    seen: list[tuple[str, Path, float, Path | None]] = []

    def run(
        command: str, cwd: Path, *, timeout: float = 55, wrapper: Path | None = None
    ) -> CheckResult:
        seen.append((command, cwd, timeout, wrapper))
        return results[command]

    run.seen = seen  # type: ignore[attr-defined]
    return run


def test_local_repos_matches_origin_not_dirname(
    make_repo: Callable[..., Path], paths: Paths
) -> None:
    odd = make_repo(
        "weird-dir", origin="git@github.com:kuhyx/demo.git", parent=paths.src_root
    )
    plain = make_repo("plain", parent=paths.src_root)
    (paths.src_root / "not-a-repo").mkdir()
    (paths.src_root / "file.txt").write_text("x")
    found = sweep.local_repos(paths.src_root)
    assert found["kuhyx/demo"] == odd
    assert found["kuhyx/plain"] == plain
    assert "kuhyx/not-a-repo" not in found


def test_local_repos_missing_root(tmp_path: Path) -> None:
    assert sweep.local_repos(tmp_path / "none") == {}


def test_sweep_reports_only_passing(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    root = make_repo(
        "weird", origin="git@github.com:kuhyx/demo.git", parent=paths.src_root
    )
    for check in ("pass-cmd", "fail-cmd", "slow-cmd", "nocmd-untrusted", "manual-cmd"):
        add_trusted(paths.trust_file, check, "t")
    client = _client(
        _task(A, "kuhyx/demo", "Passes", done_check="pass-cmd"),
        _task(B, "kuhyx/demo", "Fails", done_check="fail-cmd"),
        _task(C, "kuhyx/demo", "Slow", done_check="slow-cmd"),
        _task(D, "kuhyx/demo", "Untrusted", done_check="evil"),
        (
            line(E, "kuhyx/demo", "# Manual"),
            detail(E, text="# Manual\n\nCheck: manual", done_check="manual-cmd"),
        ),
        _task(F, "kuhyx/absent", "Not local", done_check="pass-cmd"),
    )
    runner = _runner(
        {
            "pass-cmd": CheckResult(0, False),
            "fail-cmd": CheckResult(2, False),
            "slow-cmd": CheckResult(None, True),
        }
    )
    ctx, out = make_ctx(client, root)
    assert sweep.run(ctx, runner=runner) == 0
    report = paths.report_file.read_text().splitlines()
    assert report[0] == "aaaaaaaa kuhyx/demo Passes"
    assert report[1] == "# close by hand: eeeeeeee kuhyx/demo Manual"
    assert report[-1] == (
        "# swept 6 open notes: 1 pass, 1 fail, 1 timeout, 1 untrusted, 1 manual, 1 no local repo"
    )
    assert len(report) == 3
    assert [c[0] for c in runner.seen] == ["pass-cmd", "fail-cmd", "slow-cmd"]  # type: ignore[attr-defined]
    assert all(c[1] == root and c[2] == 55 for c in runner.seen)  # type: ignore[attr-defined]
    assert out[-1] == report[-1]


def test_sweep_skips_done_and_checkless(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    root = make_repo(
        "demo", origin="git@github.com:kuhyx/demo.git", parent=paths.src_root
    )
    client = _client(
        _task(A, "kuhyx/demo", "Done", status="done", done_check="x"),
        _task(B, "kuhyx/demo", "NoCheck", done_check=None),
    )
    ctx, _ = make_ctx(client, root)
    sweep.run(ctx, runner=_runner({}))
    report = paths.report_file.read_text().splitlines()
    assert report == [
        "# swept 2 open notes: 0 pass, 0 fail, 0 timeout, 0 untrusted, 0 manual, 0 no local repo"
    ]


def test_sweep_uses_capped_wrapper(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
    tmp_path: Path,
) -> None:
    root = make_repo(
        "demo", origin="git@github.com:kuhyx/demo.git", parent=paths.src_root
    )
    add_trusted(paths.trust_file, "c", "t")
    client = _client(_task(A, "kuhyx/demo", "T", done_check="c"))
    wrapper = tmp_path / "capped.sh"
    object.__setattr__(paths, "capped", wrapper)
    runner = _runner({"c": CheckResult(0, False)})
    ctx, _ = make_ctx(client, root)
    sweep.run(ctx, runner=runner)
    assert runner.seen[0][3] == wrapper  # type: ignore[attr-defined]


def test_dry_run_runs_nothing(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    root = make_repo(
        "demo", origin="git@github.com:kuhyx/demo.git", parent=paths.src_root
    )
    add_trusted(paths.trust_file, "c", "t")
    client = _client(
        _task(A, "kuhyx/demo", "Would", done_check="c"),
        _task(B, "kuhyx/demo", "Untrusted", done_check="zz"),
    )

    def explode(*_a: object, **_k: object) -> CheckResult:
        raise AssertionError("dry run executed a check")

    ctx, _ = make_ctx(client, root)
    assert sweep.run(ctx, dry_run=True, runner=explode) == 0
    report = paths.report_file.read_text().splitlines()
    assert report[0] == "would-run aaaaaaaa kuhyx/demo Would"
    assert report[-1].startswith("# dry-run: 2 open notes: 1 would run")


def test_sweep_empty_list(
    make_ctx: Callable[..., tuple[Context, list[str]]], paths: Paths, tmp_path: Path
) -> None:
    ctx, _ = make_ctx(_client(), tmp_path)
    assert sweep.run(ctx) == 0
    assert paths.report_file.read_text().startswith("# swept 0 open notes")


def test_server_down_exits_one_and_keeps_old_report(
    make_ctx: Callable[..., tuple[Context, list[str]]], paths: Paths, tmp_path: Path
) -> None:
    paths.report_file.parent.mkdir(parents=True)
    paths.report_file.write_text("old\n")
    client = FakeClient({"list_tasks": McpUnavailable("refused")})
    ctx, out = make_ctx(client, tmp_path)
    assert sweep.run(ctx) == 1
    assert paths.report_file.read_text() == "old\n"
    assert "unavailable" in out[0]


def test_report_override_path(
    make_ctx: Callable[..., tuple[Context, list[str]]], paths: Paths, tmp_path: Path
) -> None:
    ctx, _ = make_ctx(_client(), tmp_path)
    target = tmp_path / "elsewhere" / "r.txt"
    assert sweep.run(ctx, report=target) == 0
    assert target.exists()
    assert not paths.report_file.exists()


def test_note_lookup_error_skips_that_note(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    root = make_repo(
        "demo", origin="git@github.com:kuhyx/demo.git", parent=paths.src_root
    )
    client = FakeClient(
        {
            "list_tasks": line(A, "kuhyx/demo"),
            "get_task": McpToolError("error: id: ambiguous"),
        }
    )
    ctx, _ = make_ctx(client, root)
    assert sweep.run(ctx) == 0
    assert paths.report_file.read_text().startswith("# swept 1 open notes: 0 pass")


def test_main_rejects_unknown_flag(
    make_ctx: Callable[..., tuple[Context, list[str]]], tmp_path: Path
) -> None:
    ctx, out = make_ctx(_client(), tmp_path)
    assert sweep.main(ctx, ["--nope"]) == 2
    assert "usage" in out[0]


def test_main_without_flags_uses_configured_paths(
    make_ctx: Callable[..., tuple[Context, list[str]]], paths: Paths, tmp_path: Path
) -> None:
    ctx, _ = make_ctx(_client(), tmp_path)
    assert sweep.main(ctx, []) == 0
    assert paths.report_file.exists()
