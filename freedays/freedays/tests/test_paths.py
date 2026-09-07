"""The path bundle itself, exercised unpatched.

The autouse redirect in ``conftest`` replaces ``resolve_paths`` *as imported
by* ``_api``/``_audit``/``_sync``. It does not touch ``freedays._paths``, so
the functions below are the real ones -- which is the point: the seam every
other test relies on has to be tested somewhere, and that somewhere cannot
be behind the seam.
"""

from __future__ import annotations

from pathlib import Path

from freedays._constants import (
    AUDIT_PATH,
    DEVICE_ID_PATH,
    HMAC_KEY_FILE,
    LOG_PATH,
    STATE_DIR,
    SYNC_STATE_PATH,
)
from freedays._paths import Paths, resolve_paths


def test_the_defaults_are_the_real_per_user_locations() -> None:
    defaults = Paths.default()
    assert defaults.log == LOG_PATH
    assert defaults.device_id == DEVICE_ID_PATH
    assert defaults.audit == AUDIT_PATH
    assert defaults.hmac_key == HMAC_KEY_FILE
    assert defaults.sync_state == SYNC_STATE_PATH


def test_every_default_lives_under_one_state_directory() -> None:
    """Nothing may escape ``~/.local/share/freedays``."""
    for path in vars(Paths.default()).values():
        assert isinstance(path, Path)
        assert path.parent == STATE_DIR


def test_under_relocates_every_single_file(tmp_path: Path) -> None:
    """The property the test redirect depends on: no file is left behind."""
    relocated = Paths.under(tmp_path)
    for path in vars(relocated).values():
        assert path.parent == tmp_path


def test_under_gives_each_file_a_distinct_name(tmp_path: Path) -> None:
    names = [path.name for path in vars(Paths.under(tmp_path)).values()]
    assert len(names) == len(set(names))


def test_resolve_returns_the_bundle_it_was_given(tmp_path: Path) -> None:
    explicit = Paths.under(tmp_path)
    assert resolve_paths(explicit) is explicit


def test_resolve_falls_back_to_the_defaults() -> None:
    assert resolve_paths(None) == Paths.default()
