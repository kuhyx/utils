"""Run a /leetcode coaching loop without Claude.

Entered by `leetcode --local` (Ollama only), or by the REPL mid-session when
Claude reports a usage limit (`free=True`: OmniRoute `free-best` first, Ollama
only when the gateway fails, `free_chain`) -- in which case `history` already
holds the turns so far, so the model picks up where Claude stopped instead of
starting over. Every draft passes the same no-solution gate
(`local_coach.respond`). Its prints ARE the session (T201 exemption in
pyproject.toml).
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import TYPE_CHECKING
import urllib.error

from leetcode_coach import (
    free_chain,
    local_backend,
    local_cards,
    local_coach,
    omniroute_backend,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_coach import phase

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


def _run_fetcher(
    problem: str, runner: Callable[..., subprocess.CompletedProcess[str]]
) -> subprocess.CompletedProcess[str]:
    return runner(
        [sys.executable, str(local_coach.SKILL_DIR / "fetch_problem.py"), problem],
        capture_output=True,
        text=True,
        check=False,
    )


def fetched_statement(
    problem: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str | None:
    """Statement + starter code, or None when it cannot be fetched (no prompt)."""
    proc = _run_fetcher(problem, runner)
    return proc.stdout if proc.returncode == 0 else None


def fetch_statement(
    problem: str,
    read: Callable[[], str | None],
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str | None:
    """Statement + starter code, or whatever kuhy pastes when it cannot be fetched."""
    proc = _run_fetcher(problem, runner)
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


def show(
    turn: local_coach.Turn,
    coach: local_coach.LocalCoach,
    gate: phase.PhaseGate | None = None,
) -> None:
    """Print one reply; build its cards deck, feeding rejections back."""
    for _ in range(CARD_RETRIES + 1):
        display, payload = local_cards.split_cards(turn.text)
        print(gate.after_reply(display) if gate else display)
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


def _screen(gate: phase.PhaseGate | None, block: str) -> str | None:
    """The block to send the coach (None when the phase gate refuses it)."""
    if gate is None:
        return block
    sent, note = gate.screen(block)
    if note:
        print(note)
    return sent


class GpuRefusedError(ConnectionError):
    """kuhy declined to load the local model: the chain has no rung left."""


class OllamaAfterGpuCheck:
    """The free chain's last rung: Ollama, once kuhy agrees to load it (asked once)."""

    def __init__(self) -> None:
        """Nothing asked yet."""
        self.agreed = False

    def __call__(
        self, messages: list[dict[str, str]], *, timeout: float
    ) -> local_backend.LocalReply:
        """Announce the fall-through, check the GPU once, then ask Ollama."""
        if not self.agreed:
            print(f"[OmniRoute down: local {local_backend.MODEL} via Ollama]")
            if not confirm_gpu():
                print("[not loading the local model]")
                msg = "local model declined"
                raise GpuRefusedError(msg)
            self.agreed = True
        return local_backend.chat(messages, timeout=timeout)


def free_chat(
    rung: OllamaAfterGpuCheck,
) -> Callable[[list[dict[str, str]]], local_backend.LocalReply]:
    """One session's chat: OmniRoute, then ``rung``."""

    def chat(messages: list[dict[str, str]]) -> local_backend.LocalReply:
        return free_chain.chat(messages, rungs=(omniroute_backend.chat, rung))

    return chat


def _coach(
    statement: str,
    history: list[dict[str, str]],
    gate: phase.PhaseGate | None,
    *,
    free: bool,
) -> local_coach.LocalCoach | None:
    """The coach, announced; ``None`` when kuhy declines the local model."""
    if not free and not confirm_gpu():
        print("[not loading the local model]")
        return None
    coach = local_coach.LocalCoach.start(statement, history)
    if free:
        coach.chat = free_chat(OllamaAfterGpuCheck())
    if gate is not None:
        gate.known = statement
        coach.leak_guard = gate.leaks
    label = (
        f"free: {omniroute_backend.MODEL} via OmniRoute"
        if free
        else f"local: {local_backend.MODEL} via Ollama"
    )
    print(f"[{label}]\n\n...", flush=True)
    return coach


def run(
    problem: str,
    history: list[dict[str, str]],
    first: str,
    read: Callable[[], str | None],
    gate: phase.PhaseGate | None = None,
    *,
    free: bool = False,
) -> int:
    """Coach without Claude until kuhy quits. `first` is sent before reading input.

    `free` (the usage-limit hand-over) coaches on OmniRoute first, Ollama after.
    With a `gate`, every block passes the req-before-code phase gate first and
    every reply the toolbox leak check (`first` was screened by the caller).
    """
    statement = fetch_statement(problem, read)
    if not statement:
        return 1
    try:
        coach = _coach(statement, history, gate, free=free)
        if coach is None:
            return 1
        show(coach.respond(first), coach, gate)
        while (block := read()) is not None and not is_quit(block):
            if (sent := _screen(gate, block)) is None:
                continue
            print("\n...", flush=True)
            show(coach.respond(sent), coach, gate)
    except GpuRefusedError:
        print("[neither OmniRoute nor Ollama answered: try again later]")
        return 1
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
