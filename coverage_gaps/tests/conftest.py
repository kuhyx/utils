"""Small fixture reports, one per supported format, all describing a.py/b.py.

a.py: lines 1-5 with 2,3 and 5 missed + one missed branch on line 4.
b.py: fully covered (must never be listed).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

LCOV = """TN:
SF:a.py
DA:1,1
DA:2,0
DA:3,0
DA:4,1
DA:5,0
BRDA:4,0,0,1
BRDA:4,0,1,-
end_of_record
SF:b.py
DA:1,3
end_of_record
SF:a.py
DA:1,1
DA:2,0
end_of_record
"""

COBERTURA = """<?xml version="1.0" ?>
<coverage version="7"><packages><package name="p"><classes>
<class filename="a.py"><lines>
<line number="1" hits="1"/><line number="2" hits="0"/><line number="3" hits="0"/>
<line number="4" hits="1" branch="true" condition-coverage="50% (1/2)"/>
<line number="5" hits="0"/></lines></class>
<class filename="b.py"><lines><line number="1" hits="2"/></lines></class>
<class filename="a.py"><lines><line number="1" hits="1"/></lines></class>
</classes></package></packages></coverage>
"""

JACOCO = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" "report.dtd">
<report name="x"><package name="com/x">
<sourcefile name="A.kt">
<line nr="1" mi="0" ci="3"/><line nr="2" mi="2" ci="0"/><line nr="3" mi="1" ci="0"/>
<line nr="4" mi="0" ci="4" mb="1" cb="1"/><line nr="5" mi="1" ci="0"/></sourcefile>
<sourcefile name="B.kt"><line nr="1" mi="0" ci="1"/></sourcefile>
</package><package name=""><sourcefile name="Top.kt">
<line nr="1" mi="0" ci="1"/></sourcefile></package></report>
"""

COVERAGE_JSON = json.dumps(
    {
        "files": {
            "a.py": {
                "executed_lines": [1, 4],
                "missing_lines": [2, 3, 5],
                "missing_branches": [[4, 5]],
                "summary": {"covered_branches": 1},
            },
            "b.py": {
                "executed_lines": [1],
                "missing_lines": [],
                "missing_branches": [],
            },
        }
    }
)


@pytest.fixture
def reports(tmp_path: Path) -> dict[str, Path]:
    """Write each fixture report to disk, keyed by format name."""
    out = {}
    for name, body in {
        "lcov": LCOV,
        "cobertura": COBERTURA,
        "jacoco": JACOCO,
        "json": COVERAGE_JSON,
    }.items():
        out[name] = tmp_path / f"{name}.rpt"
        out[name].write_text(body, encoding="utf-8")
    return out
