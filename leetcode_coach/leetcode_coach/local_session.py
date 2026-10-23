"""Run a /leetcode coaching loop on the local model.

Entered by `leetcode --local`, or by the REPL mid-session when Claude reports a
usage limit -- in which case `history` already holds the turns so far, so the
local model picks up where Claude stopped instead of starting over. Its prints
ARE the session (T201 exemption in pyproject.toml).
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import TYPE_CHECKING
import urllib.error

from leetcode_coach import local_backend, local_cards, local_coach

if TYPE_CHECKING:
    from collections.abc import Callable

_LOG = logging.getLogger(__name__)

CARD_RETRIES = 2
FETCH_PREMIUM = 2


def opening_message(stuck: list[str]) -> str:
    """The first user message, standing in for `/leetcode <url> [stuck on]`."""
    said = " ".join(stuck).strip()
    return "Start the session. " + (
        f"What I'm stuck on: {said}" if said else "I have not said what I'm stuck on."
    )


def is_quit(block: str) -> bool:
    """An explicit request to leave."""
    return block.strip().lower() in {"quit", "exit"}


def fetch_statement(
    problem: str,
    read: Callable[[], str | None],
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str | None:
    """Statement + starter code, or whatever kuhy pastes when it cannot be fetched."""
    proc = runner(
        [sys.executable, str(local_coach.SKILL_DIR / "fetch_problem.py"), problem],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        return proc.stdout
    why = "premium or unknown problem" if proc.returncode == FETCH_PREMIUM else ""
    print(f"[could not fetch the problem: {why or proc.stderr.strip()}]")
    print("Paste the statement and starter code, then an empty line:")
    return read()


def confirm_gpu(ask: Callable[[str], str] = input) -> bool:
    """Ask before loading ~18 GB of VRAM next to another GPU-heavy process."""
    if local_backend.model_loaded():
        return True
    hogs = local_backend.gpu_hogs()
    if not hogs:
        return True
    print("[the GPU is busy -- loading the local model would compete with:]")
    for name, mib in hogs:
        print(f"    {name}  {mib} MiB")
    answer = ask(f"Load {local_backend.MODEL} anyway? [y/N] ")
    return answer.strip().lower() in {"y", "yes"}


def show(turn: local_coach.Turn, coach: local_coach.LocalCoach) -> None:
    """Print one reply; build its cards deck, feeding rejections back."""
    for _ in range(CARD_RETRIES + 1):
        display, payload = local_cards.split_cards(turn.text)
        print(display)
        if payload is None:
            return
        ok, out = local_cards.deliver_cards(payload)
        print(out)
        if ok:
            return
        print("\n...", flush=True)
        turn = coach.respond(
            f"make_cards.py rejected the cards:\n{out}\n"
            "Fix the named card and emit the whole ```cards block again."
        )


def run(
    problem: str,
    history: list[dict[str, str]],
    first: str,
    read: Callable[[], str | None],
) -> int:
    """Coach locally until kuhy quits. `first` is sent before reading input."""
    statement = fetch_statement(problem, read)
    if not statement:
        return 1
    try:
        if not confirm_gpu():
            print("[not loading the local model]")
            return 1
        coach = local_coach.LocalCoach.start(statement, history)
        print(f"[local: {local_backend.MODEL} via Ollama]\n\n...", flush=True)
        show(coach.respond(first), coach)
        while (block := read()) is not None and not is_quit(block):
            print("\n...", flush=True)
            show(coach.respond(block), coach)
    except (urllib.error.URLError, ConnectionError) as exc:
        _LOG.warning("Ollama is not reachable: %s", exc)
        print(f"[Ollama is not reachable at {local_backend.OLLAMA_URL}: {exc}]")
        print("[start it with: systemctl start ollama]")
        return 1
    except local_backend.ContextOverflowError as exc:
        _LOG.warning("local session ended: %s", exc)
        print(f"[{exc}]")
        return 1
    return 0
