"""Parsers for lcov, Cobertura XML, JaCoCo XML and coverage.py JSON."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

from coverage_gaps.models import FileAccumulator, FileGap, ReportError, build_gap

_CONDITION = re.compile(r"\((\d+)/(\d+)\)")


def _finish(files: dict[str, FileAccumulator]) -> list[FileGap]:
    return [build_gap(path, acc) for path, acc in files.items()]


def parse_lcov(text: str) -> list[FileGap]:
    """Parse lcov.info: SF / DA / BRDA records, `end_of_record` optional."""
    files: dict[str, FileAccumulator] = {}
    acc: FileAccumulator | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("SF:"):
            acc = files.setdefault(line[3:], FileAccumulator())
        elif acc is not None and line.startswith("DA:"):
            num, hits, *_ = line[3:].split(",")
            acc.add_line(int(num), int(hits) > 0)
        elif acc is not None and line.startswith("BRDA:"):
            num, block, branch, taken = line[5:].split(",")
            covered = taken not in ("-", "0")
            acc.add_branch(int(num), int(block), _branch_id(branch), covered)
        elif line == "end_of_record":
            acc = None
    return _finish(files)


def _branch_id(branch: str) -> int:
    return int(branch) if branch.isdigit() else 0


def parse_cobertura(text: str) -> list[FileGap]:
    """Parse Cobertura `coverage.xml` (coverage.py, gcovr, ...)."""
    root = ET.fromstring(text)
    files: dict[str, FileAccumulator] = {}
    for cls in root.iter("class"):
        acc = files.setdefault(cls.get("filename", ""), FileAccumulator())
        for node in cls.iter("line"):
            num = int(node.get("number", "0"))
            acc.add_line(num, int(node.get("hits", "0")) > 0)
            match = _CONDITION.search(node.get("condition-coverage", ""))
            if match:
                hit, total = int(match[1]), int(match[2])
                for idx in range(total):
                    acc.add_branch(num, 0, idx, idx < hit)
    return _finish(files)


def parse_jacoco(text: str) -> list[FileGap]:
    """Parse JaCoCo XML: per `sourcefile` line records (mi/ci/mb/cb)."""
    root = ET.fromstring(text)
    files: dict[str, FileAccumulator] = {}
    for package in root.iter("package"):
        base = package.get("name", "")
        for source in package.iter("sourcefile"):
            name = source.get("name", "")
            acc = files.setdefault(
                f"{base}/{name}" if base else name, FileAccumulator()
            )
            for node in source.iter("line"):
                num = int(node.get("nr", "0"))
                acc.add_line(num, int(node.get("ci", "0")) > 0)
                missed_b, covered_b = int(node.get("mb", "0")), int(node.get("cb", "0"))
                for idx in range(missed_b + covered_b):
                    acc.add_branch(num, 0, idx, idx >= missed_b)
    return _finish(files)


def parse_coverage_json(text: str) -> list[FileGap]:
    """Parse `coverage json` output (with or without branch data)."""
    files: dict[str, FileAccumulator] = {}
    for path, data in json.loads(text).get("files", {}).items():
        acc = files.setdefault(path, FileAccumulator())
        for num in data.get("executed_lines", []):
            acc.add_line(num, True)
        for num in data.get("missing_lines", []):
            acc.add_line(num, False)
        missing = data.get("missing_branches", [])
        for idx, (src, _dst) in enumerate(missing):
            acc.add_branch(abs(src), 1, idx, False)
        covered = data.get("summary", {}).get("covered_branches", 0)
        for idx in range(covered):
            acc.add_branch(0, 2, idx, True)
    return _finish(files)


def detect_format(text: str) -> str:
    """Return 'lcov' | 'cobertura' | 'jacoco' | 'json' from file content."""
    head = text.lstrip()[:4000]
    if head.startswith("{"):
        return "json"
    if head.startswith("<"):
        if "<report" in head:
            return "jacoco"
        if "<coverage" in head:
            return "cobertura"
    elif re.search(r"^(TN|SF):", head, re.MULTILINE):
        return "lcov"
    raise ReportError("unrecognised coverage report format")


_PARSERS: dict[str, Callable[[str], list[FileGap]]] = {
    "lcov": parse_lcov,
    "cobertura": parse_cobertura,
    "jacoco": parse_jacoco,
    "json": parse_coverage_json,
}


def load_report(path: Path) -> tuple[str, list[FileGap]]:
    """Read and parse a report; raise ReportError on any failure."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ReportError(f"cannot read {path}: {exc.strerror}") from exc
    fmt = detect_format(text)
    try:
        return fmt, _PARSERS[fmt](text)
    except (ET.ParseError, ValueError, TypeError, AttributeError) as exc:
        raise ReportError(f"malformed {fmt} report {path}: {exc}") from exc
