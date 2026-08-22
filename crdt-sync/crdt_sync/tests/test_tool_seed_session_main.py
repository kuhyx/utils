"""Tests for ``main()`` in ``tool/seed_session``.

Split from :mod:`test_tool_seed_session` to stay under the 250-line cap.

The behaviour worth pinning here is what happens when a run dies partway. It
leaves some apps working and some not, and saying exactly which is the
difference between rerunning the ones that need it and a hunt through
``~/.config`` for what actually happened -- so the rerun line is asserted to
list the remaining apps and only those.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from crdt_sync._config import ConfigError
from crdt_sync._firebase_auth import FirebaseAuthError
from crdt_sync.tests.test_tool_seed_session import _CONFIG, _ID_VALUE
from tool import seed_session as ss
from tool.google_id_token import TokenError

_CLIENT_ID = "the-web-client-id"
_CLIENT_CREDENTIAL = "the-web-client-secret"
_ARGV = ["--client-id", _CLIENT_ID, "--client-secret", _CLIENT_CREDENTIAL]


def test_main_seeds_every_default_app(caplog: pytest.LogCaptureFixture) -> None:
    """With no --app, all of DEFAULT_APPS are seeded."""
    with (
        patch.object(ss.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(ss, "fetch_id_token", return_value=_ID_VALUE),
        patch.object(ss, "seed_apps", return_value=list(ss.DEFAULT_APPS)) as seeded,
        caplog.at_level(logging.INFO, logger="seed_session"),
    ):
        code = ss.main(_ARGV)

    assert code == 0
    assert seeded.call_args.args[2] == ss.DEFAULT_APPS
    assert f"{len(ss.DEFAULT_APPS)} desktop session(s)" in caplog.text


def test_todo_is_among_the_default_apps() -> None:
    """It grew a desktop wrapper with its own Firebase REST client.

    Its credential cache needs seeding exactly like the Python daemons, which
    is why it is no longer grouped with the phone-only Flutter apps.
    """
    assert "todo" in ss.DEFAULT_APPS


def test_a_single_app_can_be_selected() -> None:
    """--app narrows the run, which is what a rerun after a failure uses."""
    with (
        patch.object(ss.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(ss, "fetch_id_token", return_value=_ID_VALUE),
        patch.object(ss, "seed_apps", return_value=["diet_guard"]) as seeded,
    ):
        code = ss.main([*_ARGV, "--app", "diet_guard"])

    assert code == 0
    assert seeded.call_args.args[2] == ("diet_guard",)


def test_the_app_flag_is_repeatable() -> None:
    """Rerunning two failed apps should not need two invocations."""
    with (
        patch.object(ss.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(ss, "fetch_id_token", return_value=_ID_VALUE),
        patch.object(ss, "seed_apps", return_value=["diet_guard", "todo"]) as seeded,
    ):
        ss.main([*_ARGV, "--app", "diet_guard", "--app", "todo"])

    assert seeded.call_args.args[2] == ("diet_guard", "todo")


def test_an_unknown_app_is_refused_by_argparse() -> None:
    """The constrained choices exist because of a real failure.

    A typo like "diet-guard" would otherwise create ~/.config/diet-guard/,
    verify against it happily, and report PASS while the real diet_guard
    stayed dead.
    """
    with pytest.raises(SystemExit):
        ss.main([*_ARGV, "--app", "diet-guard"])


def test_the_consent_flow_receives_the_client_and_port() -> None:
    """A Web client needs the registered port verbatim, not a free one."""
    with (
        patch.object(ss.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(ss, "fetch_id_token", return_value=_ID_VALUE) as fetch,
        patch.object(ss, "seed_apps", return_value=[]),
    ):
        ss.main([*_ARGV, "--port", "9999", "--no-browser"])

    assert fetch.call_args.args == (_CLIENT_ID, _CLIENT_CREDENTIAL)
    assert fetch.call_args.kwargs == {"open_browser": False, "port": 9999}


def test_the_default_port_is_the_registered_one() -> None:
    """8765 is what is registered on the Web client as http://localhost:8765."""
    with (
        patch.object(ss.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(ss, "fetch_id_token", return_value=_ID_VALUE) as fetch,
        patch.object(ss, "seed_apps", return_value=[]),
    ):
        ss.main(_ARGV)

    assert fetch.call_args.kwargs["port"] == 8765


def test_the_expected_uid_is_announced_before_the_flow(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """So the wrong Google account can be spotted at the picker, not after."""
    with (
        patch.object(ss.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(ss, "fetch_id_token", return_value=_ID_VALUE),
        patch.object(ss, "seed_apps", return_value=[]),
        caplog.at_level(logging.INFO, logger="seed_session"),
    ):
        ss.main(_ARGV)

    assert _CONFIG.uid in caplog.text
    assert _CONFIG.email in caplog.text


@pytest.mark.parametrize(
    "failure",
    [
        ConfigError("no config"),
        FirebaseAuthError("wrong uid"),
        TokenError("consent refused"),
    ],
)
def test_the_named_failures_return_1(
    failure: Exception,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Each is reported, not raised as a traceback."""
    with (
        patch.object(ss.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(ss, "fetch_id_token", side_effect=failure),
        caplog.at_level(logging.INFO, logger="seed_session"),
    ):
        code = ss.main(_ARGV)

    assert code == 1
    assert "FAIL" in caplog.text


def test_an_unexpected_error_is_not_swallowed() -> None:
    """The reason the handler names its four types instead of Exception."""
    with (
        patch.object(ss.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(ss, "fetch_id_token", side_effect=RuntimeError("a real bug")),
        pytest.raises(RuntimeError, match="a real bug"),
    ):
        ss.main(_ARGV)


def test_a_total_failure_suggests_rerunning_every_app(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Nothing verified, so nothing may be reported as already working."""
    with (
        patch.object(ss.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(ss, "fetch_id_token", return_value=_ID_VALUE),
        patch.object(ss, "seed_apps", side_effect=ss.SeedError("all dead")),
        caplog.at_level(logging.INFO, logger="seed_session"),
    ):
        code = ss.main([*_ARGV, "--app", "diet_guard", "--app", "todo"])

    assert code == 1
    assert "already working" not in caplog.text
    assert "--app diet_guard --app todo" in caplog.text


def test_a_partial_failure_reports_what_already_works(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The apps that verified must not be reseeded needlessly."""
    partial = ss.SeedError("todo is dead", done=("diet_guard",))

    with (
        patch.object(ss.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(ss, "fetch_id_token", return_value=_ID_VALUE),
        patch.object(ss, "seed_apps", side_effect=partial),
        caplog.at_level(logging.INFO, logger="seed_session"),
    ):
        code = ss.main([*_ARGV, "--app", "diet_guard", "--app", "todo"])

    assert code == 1
    assert "already working: diet_guard" in caplog.text


def test_the_rerun_line_excludes_the_apps_that_already_work(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The whole value of the partial report is a copy-pasteable rerun."""
    partial = ss.SeedError("todo is dead", done=("diet_guard",))

    with (
        patch.object(ss.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(ss, "fetch_id_token", return_value=_ID_VALUE),
        patch.object(ss, "seed_apps", side_effect=partial),
        caplog.at_level(logging.INFO, logger="seed_session"),
    ):
        ss.main([*_ARGV, "--app", "diet_guard", "--app", "todo"])

    assert "rerun with: --app todo" in caplog.text


def test_both_credentials_are_required() -> None:
    """Neither half of the OAuth client is optional."""
    with pytest.raises(SystemExit):
        ss.main(["--client-id", _CLIENT_ID])
