"""Rebuild expected.txt, tables.json and error metadata of builtin drills.

Needs the live container. Reference = the saved solution (write drills) or the
query itself (predict drills); run it, then store what MySQL printed.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

from sql_drills import _paths, _sandbox, ensure_running

SOLUTIONS = Path(__file__).parents[1] / "sql_drills" / "tests" / "solutions"


def _reference(folder: Path, kind: str) -> str:
    if kind == "predict":
        return (folder / "query.sql").read_text()
    return (SOLUTIONS / f"{folder.name}.sql").read_text()


def _regen(folder: Path) -> None:
    meta_path = folder / "meta.json"
    meta = json.loads(meta_path.read_text())
    with _sandbox.sandbox((folder / "schema.sql").read_text()) as box:
        done = box.execute(_reference(folder, meta["kind"]))
        tables = box.tables()
    if done.ok:
        rows = "".join("\t".join(r) + "\n" for r in done.rows)
    else:
        meta |= {"error_code": done.code, "error_message": done.error}
        rows = f"ERROR {done.code}\n"
    meta_path.write_text(json.dumps(meta) + "\n")
    (folder / "expected.txt").write_text(rows)
    payload = {name: table.__dict__ for name, table in tables.items()}
    (folder / "tables.json").write_text(json.dumps(payload, indent=1) + "\n")


def main() -> None:
    ensure_running()
    for folder in sorted(_paths.builtin_dir().iterdir()):
        _regen(folder)
        sys.stdout.write(f"{folder.name}\n")


if __name__ == "__main__":
    main()
