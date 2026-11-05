"""free-llm: ask the free-model chain behind OmniRoute, return only the answer.

Use it to keep bulky input (logs, big files, pages) out of Claude's context:
the file goes to the free model, only its short answer comes back. Inputs over
CHUNK_CHARS are split, answered per part, and merged by one final call.
Exit: 0 answer printed | 2 refused (privacy) | 3 gateway/model failure.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from omniroute_offload import _privacy as privacy

ENDPOINT = "http://127.0.0.1:20128/v1/chat/completions"
KEY_FILE = Path.home() / ".config/omniroute/api_key"
DEFAULT_MODEL = "free-best"
CHUNK_CHARS = 60_000
TIMEOUT_S = 40
EXIT_REFUSED = 2
EXIT_GATEWAY = 3
SYSTEM = (
    "You are a careful assistant. Answer only from the given material, say so "
    "when it does not contain the answer, and keep the answer short and exact."
)


class GatewayError(RuntimeError):
    """The gateway or every model in the chain failed."""


def parse(argv: list[str]) -> argparse.Namespace:
    """Command-line options."""
    parser = argparse.ArgumentParser(
        prog="free-llm", description=__doc__.splitlines()[0]
    )
    parser.add_argument("prompt", help="question or instruction")
    parser.add_argument(
        "-f",
        "--file",
        action="append",
        default=[],
        type=Path,
        help="attach a file (repeatable)",
    )
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument(
        "--force",
        action="store_true",
        help="skip path/repo checks (never the credential scan)",
    )
    return parser.parse_args(argv)


def gather(args: argparse.Namespace) -> str:
    """Attached files plus piped stdin as one labelled text; raises PermissionError."""
    parts = []
    for path in args.file:
        reason = None if args.force else privacy.file_refusal(path, home=Path.home())
        if reason:
            raise PermissionError(reason)
        try:
            parts.append(f"=== {path.name} ===\n{path.read_text(errors='replace')}")
        except OSError as err:
            msg = f"cannot read {path}: {err.strerror}"
            raise PermissionError(msg) from err
    if not sys.stdin.isatty():
        piped = sys.stdin.read()
        if piped:
            parts.append(f"=== stdin ===\n{piped}")
    material = "\n\n".join(parts)
    reason = privacy.secret_refusal(f"{material}\n{args.prompt}")
    if reason:
        raise PermissionError(reason)
    return material


def split_chunks(text: str, size: int) -> list[str]:
    """Split into pieces of at most size chars, cutting at line breaks when possible."""
    chunks = []
    while text:
        cut = min(len(text), size)
        newline = text.rfind("\n", 0, cut)
        if 0 < newline < cut < len(text):
            cut = newline + 1
        chunks.append(text[:cut])
        text = text[cut:]
    return chunks


def ask(content: str, args: argparse.Namespace) -> str:
    """One chat call through the gateway; returns the answer text."""
    body = {
        "model": args.model,
        "max_tokens": args.max_tokens,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": content},
        ],
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {KEY_FILE.read_text().strip()}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            reply = json.load(resp)
    except urllib.error.HTTPError as err:
        with err:
            detail = err.read().decode(errors="replace")[:200]
        msg = f"gateway {err.code}: {detail}"
        raise GatewayError(msg) from err
    except urllib.error.URLError as err:
        msg = (
            f"gateway unreachable ({err.reason}); start it with "
            "~/src/omniroute-tetris-test/start.sh"
        )
        raise GatewayError(msg) from err
    text = str(reply["choices"][0]["message"].get("content") or "").strip()
    if not text:
        msg = f"empty answer from {reply.get('model')}"
        raise GatewayError(msg)
    usage = reply.get("usage", {})
    print(
        f"[free-llm {reply.get('model')} in={usage.get('prompt_tokens')} "
        f"out={usage.get('completion_tokens')}]",
        file=sys.stderr,
    )
    return text


def answer(material: str, args: argparse.Namespace) -> str:
    """Answer directly, or map over chunks and merge the partial answers."""
    if len(material) <= CHUNK_CHARS:
        return ask(f"{material}\n\n{args.prompt}" if material else args.prompt, args)
    chunks = split_chunks(material, CHUNK_CHARS)
    with ThreadPoolExecutor(max_workers=8) as pool:
        partial = list(
            pool.map(
                lambda c: ask(
                    f"{c}\n\n(This is one part of a larger input.) {args.prompt}", args
                ),
                chunks,
            )
        )
    merged = "\n\n".join(
        f"--- part {i}/{len(partial)} ---\n{p}" for i, p in enumerate(partial, 1)
    )
    return ask(
        f"Partial answers, one per part of the input:\n{merged}\n\n"
        f"Merge them into one answer to: {args.prompt}",
        args,
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point for the free-llm command."""
    args = parse(sys.argv[1:] if argv is None else argv)
    try:
        print(answer(gather(args), args))
    except PermissionError as err:
        print(f"free-llm refused: {err}", file=sys.stderr)
        return EXIT_REFUSED
    except GatewayError as err:
        print(f"free-llm failed: {err}", file=sys.stderr)
        return EXIT_GATEWAY
    return 0


if __name__ == "__main__":
    sys.exit(main())
