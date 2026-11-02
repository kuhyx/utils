"""Setup shared by the closer tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todo_hooks.trust import add_trusted

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todo_hooks.context import Context
    from todo_hooks.paths import Paths
    from todo_hooks.tests._fakes import FakeClient

ID = "0123abcd-0000-4000-8000-000000000001"
ID2 = "4567ef01-0000-4000-8000-000000000002"
MSG = "feat: x\n\nTodo: 0123abcd"


def setup(  # noqa: PLR0913
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
    client: FakeClient,
    *,
    check: str | None = "true",
    trust: bool = True,
    message: str = MSG,
) -> tuple[Path, Context, list[str]]:
    root = make_repo("demo", origin="git@github.com:kuhyx/demo.git", message=message)
    if trust and check:
        add_trusted(paths.trust_file, check, "test")
    ctx, lines = make_ctx(client, root)
    return root, ctx, lines
