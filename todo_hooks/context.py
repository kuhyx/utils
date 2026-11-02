"""Everything a subcommand needs, injectable so tests never touch real state."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import TYPE_CHECKING

from todo_hooks.client import McpAuthError, McpClient, McpError, McpUnavailable
from todo_hooks.paths import Paths

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from todo_hooks.client import TaskClient

PREFIX = "todo-hooks: "


@dataclass
class Context:
    """Environment, working directory, paths, client factory and output sink."""

    env: Mapping[str, str]
    cwd: Path
    paths: Paths
    make_client: Callable[[], TaskClient]
    out: Callable[[str], None]

    @classmethod
    def build(
        cls,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        make_client: Callable[[], TaskClient] | None = None,
    ) -> Context:
        """Real defaults: ``os.environ``, the cwd, ``~`` paths, a live client."""
        use_env = dict(os.environ) if env is None else dict(env)
        paths = Paths.default(use_env)

        def live() -> TaskClient:
            return McpClient.from_env(use_env, paths.token_file)

        return cls(
            env=use_env,
            cwd=cwd or Path.cwd(),
            paths=paths,
            make_client=make_client or live,
            out=print,
        )

    def say(self, message: str) -> None:
        self.out(PREFIX + message)


def describe(err: McpError) -> str:
    """Server-side failures read as 'unavailable'; tool errors verbatim."""
    if isinstance(err, McpUnavailable | McpAuthError):
        return f"todo server unavailable ({err})"
    return str(err)
