# Copyright (c) 2026 Krzysztof Rudnicki
"""Command line: hear a section of the article, or render a recipe to a file.

Subcommands: ``list``, ``explain <demo|all>``, ``demo <demo|all> --out DIR``
and ``render --recipe recipe.json --out bed.wav [--manifest m.json]``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from music_theory import compose, demos, manifest, wav

if TYPE_CHECKING:
    from music_theory.demo_support import Demo


def _emit(line: str) -> None:
    sys.stdout.write(line + "\n")


def build_parser() -> argparse.ArgumentParser:
    """The argument parser, separate from ``main`` so it can be tested."""
    parser = argparse.ArgumentParser(prog="music_theory", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="names of every demo")
    explain = sub.add_parser("explain", help="print a demo's facts without rendering")
    explain.add_argument("name", help="demo name or 'all'")
    demo = sub.add_parser("demo", help="render a demo to WAV and print its facts")
    demo.add_argument("name", help="demo name or 'all'")
    demo.add_argument("--out", type=Path, required=True, help="directory for the WAVs")
    render = sub.add_parser("render", help="render a recipe JSON to a WAV")
    render.add_argument("--recipe", type=Path, required=True, help="recipe JSON file")
    render.add_argument("--out", type=Path, required=True, help="WAV to write")
    render.add_argument("--manifest", type=Path, help="manifest JSON to update")
    render.add_argument(
        "--degrade", type=float, help="override the recipe's degrade amount"
    )
    return parser


def cmd_list() -> int:
    """Print every demo name with its article section."""
    for name, builder in demos.REGISTRY.items():
        _emit(f"{name:12s} {builder.__doc__ or ''}")
    return 0


def cmd_explain(name: str) -> int:
    """Print the facts of one or all demos."""
    for demo_name in demos.selected(name):
        _print_demo(demos.run(demo_name))
    return 0


def cmd_demo(name: str, out_dir: Path) -> int:
    """Render one or all demos into ``out_dir`` and print how to hear them."""
    for index, demo_name in enumerate(demos.selected(name)):
        demo = demos.run(demo_name)
        path = wav.write(out_dir / f"{index + 1:02d}_{demo_name}.wav", demo.signal)
        _print_demo(demo)
        _emit(f"  hear it: {wav.play_command(path)}")
    return 0


def cmd_render(
    recipe_path: Path, out: Path, manifest_path: Path | None, degrade: float | None
) -> int:
    """Render a recipe file to a WAV and record it in the manifest."""
    data = json.loads(recipe_path.read_text())
    if not isinstance(data, dict):
        _emit(f"error: {recipe_path} does not hold a recipe object")
        return 1
    recipe = compose.Recipe.from_dict(data)
    if degrade is not None:
        recipe = compose.with_degrade(recipe, degrade)
    signal = compose.compose(recipe)
    wav.write(out, signal, recipe.sample_rate)
    record = manifest.entry(recipe, out, signal)
    if manifest_path is not None:
        entries = manifest.read(manifest_path) if manifest_path.exists() else {}
        entries[out.name] = record
        manifest.write(manifest_path, entries)
    _emit(f"{out}: {record['seconds']:.2f} s, sha256 {record['sha256']}")
    return 0


def _print_demo(demo: Demo) -> None:
    _emit(f"[{demo.section}] {demo.name}")
    for fact in demo.facts:
        _emit(f"  {fact}")


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit code."""
    args = build_parser().parse_args(argv)
    if args.command == "list":
        return cmd_list()
    if args.command == "explain":
        return cmd_explain(args.name)
    if args.command == "demo":
        return cmd_demo(args.name, args.out)
    return cmd_render(args.recipe, args.out, args.manifest, args.degrade)
