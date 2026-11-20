import subprocess
from pathlib import Path

import pytest

from kuhy_credit import TEXT, URL, credit_line, terminal

CREDIT_DIR = Path(__file__).resolve().parents[1]


def test_credit_line_is_text_then_url() -> None:
    assert credit_line() == "Created by kuhy https://kuhy.duckdns.org"
    assert (TEXT, URL) == ("Created by kuhy", "https://kuhy.duckdns.org")


def test_main_prints_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    assert terminal.main() == 0
    assert capsys.readouterr().out == "Created by kuhy https://kuhy.duckdns.org\n"


def test_shell_helper_prints_the_same_line() -> None:
    out = subprocess.run(
        [str(CREDIT_DIR / "terminal/kuhy-credit.sh")], check=True, capture_output=True, text=True
    ).stdout
    assert out == credit_line() + "\n"
