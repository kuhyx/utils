"""Exit codes and the one error type every verb raises."""

from __future__ import annotations

EXIT_OK = 0
EXIT_FAIL = 1  # the step ran and its check failed: not found, timeout, page exception
EXIT_USAGE = 2  # bad arguments
EXIT_BROWSER = 3  # no driver browser reachable (not started, crashed, CDP gone)
EXIT_UNSAFE = 4  # the CDP port belongs to a browser we must not drive


class DriveError(Exception):
    """A verb failed at ``step``; ``code`` becomes the process exit code."""

    def __init__(self, step: str, message: str, code: int = EXIT_FAIL) -> None:
        """Record the failing step, a one-line reason and the exit code."""
        super().__init__(f"{step}: {message}")
        self.step = step
        self.message = message
        self.code = code
