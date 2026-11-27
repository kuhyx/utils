"""THE exclude list: which changed paths count as code, docs or dropped churn.

One ordered constant, first match wins. A pattern ending in "/" matches any
directory component of the path; any other pattern is a glob on the file name.
Excluded directories come first so nothing inside node_modules/ or addons/ is
rescued by a later rule; the code keeps come before the file excludes so
package.json survives `*.json`; translation dirs come before `*.json` so
locales/en.json counts as docs, like the article's "+800k translations and docs".

Judgment calls, calibrated on the 30-day top-40 churn list (2026-11-27):
- `*.txt` is data (one word list was ~10% of all churn) except requirements/CMake.
- `*.json` is data (eval dumps, fixtures, baselines) except a few config names.
- Godot `addons/` is vendored (GUT, copies of dev_tools) except the source of
  kuhy's own addon under `godot_dev_tools/`; `*.tres` is data; `*.import`/`*.uid` are
  generated; `*.tscn` scenes stay code (authored structure).
- `fixtures/` is test data; test code itself stays.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Literal

Bucket = Literal["code", "docs", "excluded"]

RULES: tuple[tuple[Bucket, str], ...] = (
    # kuhy's own Godot addon source (utils/godot_dev_tools); games carry vendored copies
    ("code", "godot_dev_tools/"),
    # vendored, generated and data directories (any depth)
    *(
        ("excluded", d)
        for d in (
            "node_modules/", "vendor/", "third_party/", "addons/", ".venv/", ".dart_tool/",
            "dist/", "build/", "generated/", "htmlcov/", "coverage/", "__snapshots__/",
            "data/", "assets/", "fixtures/",
        )
    ),
    # config files that would otherwise fall under a data glob below
    *(
        ("code", f)
        for f in ("package.json", "tsconfig*.json", "jsconfig.json", "deno.json",
                  "requirements*.txt", "CMakeLists.txt")
    ),
    # translations and docs directories
    *(("docs", d) for d in ("docs/", "doc/", "l10n/", "locales/", "i18n/", "translations/")),
    # lockfiles
    *(
        ("excluded", f)
        for f in ("*.lock", "*.lockb", "package-lock.json", "npm-shrinkwrap.json",
                  "pnpm-lock.yaml", "go.sum")
    ),
    # generated files
    *(
        ("excluded", f)
        for f in ("*.g.dart", "*.freezed.dart", "*.mocks.dart", "*.gr.dart", "*.pb.go",
                  "*_pb2.py", "*.min.js", "*.min.css", "*.map", "coverage.xml", "lcov.info",
                  "*.lcov", "*.import", "*.uid", "*.snap")
    ),
    # data and assets
    *(
        ("excluded", f)
        for f in ("*.json", "*.jsonl", "*.ndjson", "*.geojson", "*.csv", "*.tsv", "*.txt",
                  "*.tcx", "*.gpx", "*.tres", "*.svg", "*.log")
    ),
    # docs and translations
    *(
        ("docs", f)
        for f in ("*.md", "*.mdx", "*.rst", "*.adoc", "*.arb", "*.po", "*.pot",
                  "LICENSE*", "COPYING*")
    ),
)


def classify(path: str) -> Bucket:
    """Bucket for one repo-relative path (binaries are handled by the caller)."""
    *dirs, name = path.split("/")
    for bucket, pattern in RULES:
        if pattern.endswith("/"):
            if any(fnmatchcase(d, pattern[:-1]) for d in dirs):
                return bucket
        elif fnmatchcase(name, pattern):
            return bucket
    return "code"
