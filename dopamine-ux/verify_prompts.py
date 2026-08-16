#!/usr/bin/env python3
"""Verify every path and symbol cited in the dopamine-ux prompt files.

A copy-pasteable prompt that points at a file which does not exist is worse than
no prompt, so this gate adjudicates with an exit code rather than by eye.

Two checks:
  1. Every cited on-disk path resolves.
  2. Every cited symbol is greppable in the file it is attributed to. A path
     check alone cannot catch a stale line number; a symbol grep can.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROMPT_DIR = Path.home() / "utils" / "dopamine-ux"
HOME = Path.home()

PATH_RE = re.compile(r"`(~?/[^`\s]+|[\w.\-]+/[\w./\-]+\.\w+)`")

# Not on-disk paths despite matching the shape above.
SKIP_SUBSTRINGS = (
    "://",
    "$",
    "*",
    "<",
    ">",
    "…",
    "devices/",  # Firebase/crdt key path
    "settings/advanced",  # Firebase key path
    "android.permission",
    "android.intent",
    "/sdcard/",
    "/etc/",
    "/dev/input/",
    "/opt/",
    "com.kuhy",
    "app-release.apk",
    "build/app/outputs",  # build outputs
    "flutter/services.dart",
    "flutter/material.dart",  # package imports
)

# Files a prompt CREATES. Citing them forward is correct, so absence is expected
# -- but pairing each with its creating prompt still catches a typo.
CREATED_BY_PROMPT = {
    "~/utils/unified-design-system/motion.md": "01",
    "~/utils/unified-design-system/scripts/structural_check.py": "02",
}

# Cited precisely to state that they do NOT exist.
ASSERTED_ABSENT = {"~/gatelock"}

# Generic prose fragments rather than citations of one specific file.
PROSE_FRAGMENTS = {"lib/ui/theme.dart", "lib/main.dart", "pubspec.yaml"}

# Symbols each prompt claims exist, as (repo-relative file, symbol).
SYMBOL_CLAIMS = [
    ("~/diet-guard/app/lib/screens/log_meal_screen.dart", "_onLogMeal"),
    ("~/diet-guard/app/lib/widgets/today_progress_card.dart", "TodayProgressCard"),
    ("~/diet-guard/app/lib/widgets/streak_summary_row.dart", "StreakSummaryRow"),
    ("~/diet-guard/app/lib/screens/log_meal_progress.dart", "buildTodayProgress"),
    ("~/diet-guard/app/lib/services/app_settings_service.dart", "_writeToDisk"),
    ("~/screen-locker/screen_locker/_status_types.py", "StatusSnapshot"),
    ("~/screen-locker/screen_locker/_extra_benefits.py", "process_week_transition"),
    ("~/screen-locker/screen_locker/_extra_benefits.py", "current_streak"),
    ("~/screen-locker/screen_locker/_unlock_view.py", "unlock_screen"),
    ("~/screen-locker/screen_locker/_log_mixin.py", "write_signed_entry"),
    ("~/screen-locker/screen_locker/tests/conftest.py", "_ISOLATED_STATE"),
    ("~/screen-locker/screen_locker/_weekly_check.py", "WEEKLY_WORKOUT_MINIMUM"),
    (
        "~/screen-locker/stronglift_replacement/workout_app/lib/screens/"
        "workout_screen_session.dart",
        "_playBreakEndCue",
    ),
    (
        "~/screen-locker/stronglift_replacement/workout_app/lib/screens/"
        "workout_screen_finish.dart",
        "_persistFinishedWorkout",
    ),
    (
        "~/screen-locker/stronglift_replacement/workout_app/lib/widgets/"
        "workout_summary_dialog.dart",
        "WorkoutSummaryDialog",
    ),
    (
        "~/screen-locker/stronglift_replacement/workout_app/lib/services/"
        "storage_service.dart",
        "_getSetting",
    ),
    (
        "~/screen-locker/stronglift_replacement/workout_app/lib/widgets/"
        "exercise_tile_rows.dart",
        "AnimatedContainer",
    ),
    ("~/todo/lib/data/app_settings.dart", "withAdvancedMode"),
    ("~/todo/lib/ui/settings_screen.dart", "SwitchListTile"),
    ("~/dufs-cloud/web/src/hooks/use-cloud-index.ts", "walkInto"),
    ("~/dufs-cloud/app/lib/services/cloud_index.dart", "buildCloudIndex"),
    ("~/dufs-cloud/web/src/lib/download.ts", "buildSelectionZip"),
    ("~/dufs-cloud/app/lib/services/download_zip.dart", "buildSelectionZip"),
    ("~/wake-alarm/phone_app/lib/screens/home_screen.dart", "_setPhoneAlarm"),
    ("~/wake-alarm/wake_alarm/_audio.py", "_play_on_all_sinks"),
    ("~/utils/unified-design-system/scripts/palette_check.py", "NON_COLOUR_CSS"),
    ("~/utils/unified-design-system/scripts/palette_map.py", "PALETTE"),
    ("~/utils/design_system/lib/src/feedback.dart", "showToast"),
    ("~/utils/design_system/lib/src/tokens.dart", "AppSpacing"),
    ("~/utils/gatelock/gatelock/_window.py", "LockConfig"),
]


def expand(raw: str) -> Path:
    return HOME / raw[2:] if raw.startswith("~/") else Path(raw)


def candidate_paths(text: str) -> set[str]:
    return {
        raw
        for raw in PATH_RE.findall(text)
        if not any(s in raw for s in SKIP_SUBSTRINGS)
        and raw not in PROSE_FRAGMENTS
        and not re.search(r"\.\w+:\d+$", raw)  # trailing :line suffix
    }


def prompt_roots(text: str) -> list[Path]:
    roots = []
    for label in ("Repo", "App", "Flutter app"):
        for m in re.finditer(rf"{label}: `(~/[^`]+)`", text):
            roots.append(expand(m.group(1)))
    return roots


def check_paths() -> list[str]:
    failures = []
    checked = 0
    for prompt in sorted(PROMPT_DIR.glob("*.md")):
        text = prompt.read_text()
        roots = prompt_roots(text)
        for raw in sorted(candidate_paths(text)):
            if raw in ASSERTED_ABSENT:
                if expand(raw).exists():
                    failures.append(
                        f"{prompt.name}: `{raw}` is asserted ABSENT but EXISTS"
                    )
                continue
            if raw in CREATED_BY_PROMPT:
                owner = CREATED_BY_PROMPT[raw]
                cites_owner = re.search(rf"[Pp]rompt {owner}", text) is not None
                if not prompt.name.startswith(owner) and not cites_owner:
                    failures.append(
                        f"{prompt.name}: cites `{raw}` without noting prompt "
                        f"{owner} creates it"
                    )
                continue

            checked += 1
            if raw.startswith(("~/", "/")):
                if not expand(raw).exists():
                    failures.append(f"{prompt.name}: `{raw}` MISSING")
            elif not any((r / raw).exists() for r in roots):
                failures.append(
                    f"{prompt.name}: `{raw}` not found under any of "
                    f"{[str(r) for r in roots]}"
                )
    print(f"paths: checked {checked}")
    return failures


def check_symbols() -> list[str]:
    failures = []
    for raw_file, symbol in SYMBOL_CLAIMS:
        path = expand(raw_file)
        if not path.exists():
            failures.append(f"symbol source MISSING: {raw_file}")
            continue
        if symbol not in path.read_text(errors="replace"):
            failures.append(f"symbol `{symbol}` NOT FOUND in {raw_file}")
    print(f"symbols: checked {len(SYMBOL_CLAIMS)}")
    return failures


def main() -> int:
    n_prompts = len(list(PROMPT_DIR.glob("*.md")))
    print(f"verifying {n_prompts} prompt files in {PROMPT_DIR}")
    failures = check_paths() + check_symbols()
    if failures:
        print(f"\nFAIL -- {len(failures)} problem(s):")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\nPASS -- every cited path exists and every cited symbol is present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
