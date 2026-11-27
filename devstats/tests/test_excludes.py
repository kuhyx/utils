"""The one exclude list decides what counts as code, docs or dropped churn."""

from __future__ import annotations

import pytest

from devstats.excludes import RULES, classify


@pytest.mark.parametrize(
    ("path", "bucket"),
    [
        ("src/main.py", "code"),
        ("tests/test_main.py", "code"),
        ("lib/screen.dart", "code"),
        ("scenes/level.tscn", "code"),
        ("Makefile", "code"),
        ("package.json", "code"),
        ("web/tsconfig.app.json", "code"),
        ("requirements-dev.txt", "code"),
        ("native/CMakeLists.txt", "code"),
        # lockfiles
        ("web/pnpm-lock.yaml", "excluded"),
        ("package-lock.json", "excluded"),
        ("uv.lock", "excluded"),
        ("app/pubspec.lock", "excluded"),
        ("go.sum", "excluded"),
        # generated
        ("lib/model.g.dart", "excluded"),
        ("lib/model.freezed.dart", "excluded"),
        ("static/app.min.js", "excluded"),
        ("coverage.xml", "excluded"),
        ("icon.svg.import", "excluded"),
        ("player.gd.uid", "excluded"),
        ("android/build/reports/problems/problems-report.html", "excluded"),
        ("web/dist/index.js", "excluded"),
        # vendored
        ("web/node_modules/x/index.js", "excluded"),
        ("addons/gut/gut.gd", "excluded"),
        ("game/addons/dev_tools/panel.gd", "excluded"),
        ("godot_dev_tools/addons/dev_tools/panel.gd", "code"),
        ("third_party/lib.c", "excluded"),
        ("vendor/pkg/a.go", "excluded"),
        # data / assets
        ("pacman/words.txt", "excluded"),
        ("tools/eval/data/reference.json", "excluded"),
        ("assets/audio/MANIFEST.json", "excluded"),
        ("tests/fixtures/run.tcx", "excluded"),
        ("tests/fixtures/host/q.py", "code"),
        ("app/lib/data/repo.dart", "code"),
        ("app/lib/data/repo.g.dart", "excluded"),
        ("assets/fonts/Inter.ttf.txt", "excluded"),
        ("web/build/main.js", "excluded"),
        ("games/chips/sea.tres", "excluded"),
        ("report.csv", "excluded"),
        # docs and translations
        ("README.md", "docs"),
        ("docs/guide.py", "docs"),
        ("lib/l10n/app_pl.arb", "docs"),
        ("public/locales/en.json", "docs"),
        ("LICENSE", "docs"),
        # an excluded dir beats a docs file and a code keep
        ("node_modules/x/README.md", "excluded"),
        ("node_modules/x/package.json", "excluded"),
    ],
)
def test_classify(path: str, bucket: str) -> None:
    assert classify(path) == bucket


def test_rules_use_known_buckets_only() -> None:
    assert {bucket for bucket, _ in RULES} == {"code", "docs", "excluded"}
