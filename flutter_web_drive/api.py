"""Driver: the verbs the CLI and the MCP server share (no logic lives in either)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from flutter_web_drive import actions, browser, cdp, state
from flutter_web_drive.errors import EXIT_BROWSER, EXIT_UNSAFE, EXIT_USAGE, DriveError

CDP_UP_TIMEOUT = 15.0
FLUTTER_BOOT_TIMEOUT = 30.0
# One verb must finish inside the 60 s per-action cap, screenshot included.
MAX_WAIT = 50.0


class Driver:
    """Verbs for one named app; ``start`` records the CDP port, the rest attach to it."""

    def __init__(
        self,
        app: str = "default",
        *,
        cdp_port: int | None = None,
        root: Path | None = None,
        fetch: cdp.Fetch = cdp.http_json,
        create: Callable[[str], cdp.Socket] = cdp.create_socket,
        runner: browser.Runner = browser.run,
        clock: actions.Clock | None = None,
    ) -> None:
        """Bind to ``app``'s state under ``root`` (default ~/data/claude-scratch/e2e)."""
        self.app = app
        self.cdp_port = cdp_port
        self.root = root or state.artefact_root()
        self.fetch = fetch
        self.create = create
        self.runner = runner
        self.clock = clock or actions.Clock()

    @property
    def app_dir(self) -> Path:
        """Artefacts for this app (screenshots, state)."""
        return self.root / self.app

    def _connect(self, port: int) -> cdp.Session:
        return cdp.connect(port, fetch=self.fetch, create=self.create)

    @contextmanager
    def _session(self) -> Iterator[cdp.Session]:
        port = self.cdp_port
        if port is None:
            saved = state.load(self.root, self.app)
            if saved is None:
                raise DriveError(
                    "connect",
                    f"no running browser for app {self.app!r}; run start first",
                    EXIT_BROWSER,
                )
            port = saved.cdp_port
        sess = self._connect(port)
        try:
            yield sess
        finally:
            sess.close()

    def _await_flutter(self, sess: cdp.Session) -> str:
        deadline = self.clock.now() + FLUTTER_BOOT_TIMEOUT
        while not sess.evaluate(actions.semantics.FLUTTER_READY_JS):
            if self.clock.now() >= deadline:
                raise DriveError(
                    "start",
                    f"Flutter never booted within {FLUTTER_BOOT_TIMEOUT:g}s; see `console`",
                )
            self.clock.sleep(actions.POLL)
        actions.ensure_semantics(sess, self.clock)
        width, height = actions.viewport(sess)
        return f"viewport {width}x{height}"

    def start(
        self,
        url: str,
        profile: Path,
        cdp_port: int,
        *,
        unit: str | None = None,
        size: str = "1400x1000",
    ) -> str:
        """Launch (or reuse) the headless unit on ``url`` and enable semantics."""
        unit = unit or f"fwd-{self.app}"
        dims = browser.parse_size(size)
        saved = state.State(unit=unit, cdp_port=cdp_port, url=url, profile=str(profile))
        if browser.unit_active(unit, self.runner):
            sess = self._connect(cdp_port)
            state.save(self.root, self.app, saved)
            try:
                if not str(sess.evaluate("location.href")).startswith(url):
                    sess.call("Page.navigate", url=url)
                return f"reused {unit}: {url} on CDP {cdp_port}, {self._await_flutter(sess)}"
            finally:
                sess.close()
        if cdp.probe(cdp_port, fetch=self.fetch) is not None:
            raise DriveError(
                "start",
                f"CDP port {cdp_port} is already in use by another browser",
                EXIT_UNSAFE,
            )
        profile.mkdir(parents=True, exist_ok=True)
        self.runner(["systemctl", "--user", "reset-failed", unit])
        argv = browser.unit_argv(
            unit, browser.chromium_argv(url, profile, cdp_port, dims)
        )
        if (rc := self.runner(argv)) != 0:
            raise DriveError("start", f"systemd-run exited {rc}", EXIT_BROWSER)
        deadline = self.clock.now() + CDP_UP_TIMEOUT
        while cdp.probe(cdp_port, fetch=self.fetch) is None:
            if self.clock.now() >= deadline:
                raise DriveError(
                    "start",
                    f"CDP port {cdp_port} never answered; journalctl --user -u {unit}",
                    EXIT_BROWSER,
                )
            self.clock.sleep(actions.POLL)
        state.save(self.root, self.app, saved)
        sess = self._connect(cdp_port)
        try:
            return (
                f"started {unit}: {url} on CDP {cdp_port}, {self._await_flutter(sess)}"
            )
        finally:
            sess.close()

    def stop(self) -> str:
        """Stop the unit (profile kept) and forget the state."""
        saved = state.load(self.root, self.app)
        unit = saved.unit if saved else f"fwd-{self.app}"
        self.runner(["systemctl", "--user", "stop", unit])
        state.clear(self.root, self.app)
        return f"stopped {unit}"

    def _artefact(self, kind: str) -> Path:
        return self.app_dir / f"{kind}-{state.stamp()}.png"

    def shot(self, out: Path | None = None, *, min_colours: int = 0) -> str:
        """Screenshot to ``out`` (default: a timestamped file in the app dir)."""
        with self._session() as sess:
            return actions.screenshot(sess, out or self._artefact("shot"), min_colours)

    def tree(
        self, *, filt: str | None = None, show_all: bool = False, row: str | None = None
    ) -> str:
        """Compact semantics listing."""
        with self._session() as sess:
            nodes = actions.ensure_semantics(sess, self.clock)
            return actions.semantics.format_tree(
                nodes, filt=filt, show_all=show_all, row=row
            )

    def tap(self, label: str, *, contains: bool = False) -> str:
        """Click a node by label."""
        with self._session() as sess:
            return actions.tap(sess, self.clock, label, contains=contains)

    def tap_xy(self, x: float, y: float) -> str:
        """Click at coordinates."""
        with self._session() as sess:
            return actions.tap_xy(sess, x, y)

    def text(self, value: str) -> str:
        """Insert text into the focused field."""
        with self._session() as sess:
            return actions.insert_text(sess, value)

    def key(self, name: str) -> str:
        """Press one named key."""
        with self._session() as sess:
            return actions.press_key(sess, name)

    def scroll(
        self, dx: float, dy: float, *, at: tuple[float, float] | None = None
    ) -> str:
        """Mouse-wheel scroll."""
        with self._session() as sess:
            return actions.scroll(sess, dx, dy, at)

    def wait(
        self,
        label: str,
        *,
        timeout: float = 10.0,
        contains: bool = False,
        gone: bool = False,
        flag: str | None = None,
        row: str | None = None,
    ) -> str:
        """Poll for a label (with ``flag``, or its absence); on timeout save a screenshot and fail."""
        if timeout > MAX_WAIT:
            raise DriveError(
                "wait",
                f"--timeout must be <= {MAX_WAIT:g} s (one call stays under the 60 s cap)",
                EXIT_USAGE,
            )
        with self._session() as sess:

            def snap() -> str:
                out = self._artefact("wait-timeout")
                actions.screenshot(sess, out)
                return str(out)

            return actions.wait_for(
                sess,
                self.clock,
                label,
                timeout=timeout,
                contains=contains,
                gone=gone,
                flag=flag,
                row=row,
                on_timeout=snap,
            )

    def eval(self, expr: str) -> str:
        """Evaluate JS; JSON result."""
        with self._session() as sess:
            return actions.evaluate(sess, expr)

    def console(
        self, *, limit: int = 20, warnings: bool = False, fail_on_error: bool = False
    ) -> str:
        """Recent console errors; ``fail_on_error`` turns any error into a failure."""
        with self._session() as sess:
            out, errors = actions.console(sess, limit, warnings=warnings)
        if fail_on_error and errors:
            raise DriveError("console", f"{errors} console error(s):\n{out}")
        return out
