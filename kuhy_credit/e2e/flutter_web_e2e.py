"""Flutter-web E2E: the built example app in headless chromium, real clicks.

    (cd kuhy_credit/flutter/example && flutter build web --release)
    python3 kuhy_credit/e2e/flutter_web_e2e.py [shots_dir]

The logo and the panel are found through Flutter's semantics DOM (both are
named "Created by kuhy": the logo is the button, the panel the link). Passes
when the logo click shows the panel, the panel click "opens" the URL
(window.open stubbed, which url_launcher_web calls) and the panel is gone.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from browser import CREDIT, REPO, Page, session, wait_for

BUILD = REPO / "kuhy_credit/flutter/example/build/web"
FIND = """(() => {
  const want = %s;
  const el = [...document.querySelectorAll('flt-semantics, a, [role]')].find(e =>
    (e.getAttribute('aria-label') || e.textContent || '').trim() === %s &&
    (want === 'button' ? e.getAttribute('role') === 'button'
                       : e.tagName === 'A' || e.getAttribute('role') === 'link'));
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return r.width > 0 ? [r.x + r.width / 2, r.y + r.height / 2] : null;
})()"""


def find(page: Page, role: str) -> tuple[float, float] | None:
    text = repr(CREDIT["text"]).replace("'", '"')
    return page.eval(FIND % (f'"{role}"', text))


def main() -> int:
    shots = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not (BUILD / "index.html").is_file():
        raise SystemExit(f"no web build at {BUILD}: run flutter build web first")
    with session(BUILD) as (page, port):
        page.s.call("Page.navigate", url=f"http://127.0.0.1:{port}/index.html")
        logo = wait_for(lambda: find(page, "button"), "the logo in the semantics tree", 40)
        assert find(page, "link") is None, "panel visible before any click"
        if shots:
            page.shot(shots / "flutter-web-closed.png")
        page.click(*logo)
        panel = wait_for(lambda: find(page, "link"), "the panel after the logo click")
        time.sleep(0.3)
        if shots:
            page.shot(shots / "flutter-web-open.png")
        assert page.opened() == [], "the logo click opened the site"
        page.click(*panel)
        wait_for(page.opened, "window.open after the panel click")
        assert page.opened() == [CREDIT["url"]], page.opened()
        wait_for(lambda: find(page, "link") is None, "the panel to close")
        page.click(*logo)
        wait_for(lambda: find(page, "link"), "reopen")
        page.click(*logo)
        wait_for(lambda: find(page, "link") is None, "second logo click to close")
        page.click(*logo)
        wait_for(lambda: find(page, "link"), "reopen")
        page.click(20, 20)
        wait_for(lambda: find(page, "link") is None, "outside click to close")
        assert page.opened() == [CREDIT["url"]], "a close path opened the site"
    print(f"flutter web e2e: two clicks opened {CREDIT['url']}; close paths pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
