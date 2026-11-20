"""Web E2E: the <kuhy-credit> demo page in headless chromium, real input events.

    PYTHONPATH=<repo> python3 kuhy_credit/e2e/web_e2e.py [shots_dir]

Passes when: only the logo shows; a logo click opens the panel; a panel click
"opens" CREDIT url (window.open stubbed) and closes it; Escape, an outside
click and a second logo click each close it without opening anything; Tab +
Enter reach and open it; the page made no request off loopback.
"""

from __future__ import annotations

import sys
from pathlib import Path

from browser import CREDIT, REPO, Page, session, wait_for

HOST = "document.querySelector('kuhy-credit')"


def centre(page: Page, part: str) -> tuple[float, float]:
    r = page.eval(f"(() => {{ const r = {HOST}.shadowRoot.querySelector('{part}').getBoundingClientRect();"
                  " return [r.x + r.width / 2, r.y + r.height / 2]; })()")  # fmt: skip
    return r[0], r[1]


def is_open(page: Page) -> bool:
    return bool(page.eval(f"{HOST}.open"))


def run(page: Page, port: int, theme: str, shots: Path | None) -> None:
    url = f"http://127.0.0.1:{port}/kuhy_credit/web/demo/index.html?theme={theme}"
    page.s.call("Page.navigate", url=url)
    wait_for(
        lambda: page.eval(
            f"!!{HOST} && !!customElements.get('kuhy-credit') && !!{HOST}.shadowRoot"
        ),
        "element",
    )
    assert not is_open(page), "panel visible before any click"
    assert page.eval(f"{HOST}.shadowRoot.querySelector('button').textContent.trim()") == ""
    if shots:
        page.shot(shots / f"web-{theme}-closed.png")
    page.click(*centre(page, "button"))
    assert is_open(page), "logo click did not open the panel"
    assert page.eval(f"{HOST}.shadowRoot.querySelector('a').textContent.trim()") == CREDIT["text"]
    if shots:
        page.shot(shots / f"web-{theme}-open.png")
    page.click(*centre(page, "a"))
    assert page.opened() == [CREDIT["url"]], page.opened()
    assert not is_open(page), "panel stayed open after opening the site"

    for name, close in (
        ("escape", lambda: page.key("Escape", "Escape", 27)),
        ("outside", lambda: page.click(20, 20)),
        ("second logo click", lambda: page.click(*centre(page, "button"))),
    ):
        page.click(*centre(page, "button"))
        assert is_open(page), f"reopen before {name}"
        close()
        assert not is_open(page), f"{name} did not close the panel"
    page.click(20, 20)
    page.key("Tab", "Tab", 9)
    page.key("Enter", "Enter", 13, "\r")
    assert is_open(page), "Tab + Enter did not open the panel"
    assert page.opened() == [CREDIT["url"]], "a close path opened the site"
    foreign = page.foreign_requests()
    assert not foreign, f"network requests off loopback: {foreign}"


def main() -> int:
    shots = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    with session(REPO) as (page, port):
        for theme in ("dark", "light"):
            run(page, port, theme, shots)
    print(f"web e2e: two clicks opened {CREDIT['url']}; all close paths pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
