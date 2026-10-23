"""`leetcode due`, `leetcode --cluster <name>` and `leetcode --retest <slug>`.

TODO-coach.md decisions 10 and 12, on top of `progress` (which derives
everything from the session logs):

* ``due`` lists the cold re-tests that are due (+3 and +10 days after a solve).
* ``--cluster <name>`` serves that cluster's due re-test first, else its next
  problem with no ``code`` event, skipping problems LeetCode already reports
  Accepted. The live check fails OPEN: if LeetCode cannot be asked, the
  problem is served rather than skipped.
* ``--retest <slug>`` starts a cold session: a fresh ``claude -p`` session
  with no history, whose opening tells the coach it is a re-test judged in
  ``node`` and that kuhy must NOT submit -- a resubmission is a new
  submission id, and the harvester mints a gate credit for every one.
  A ``retest`` event is logged only if the session reached a post-mortem, so
  quitting early does not burn the re-test.

``--dry-run`` says what would be served without starting a session. The
cluster name reaches the session writer through ``$LEETCODE_COACH_CLUSTER``.
Its prints are its interface (T201 exemption in pyproject.toml).
"""

from __future__ import annotations

from collections.abc import Callable
import logging
import os
import sys

from leetcode_coach import progress
from leetcode_guard._live_solved import check_solved
from leetcode_guard._settings import build_client

_logger = logging.getLogger(__name__)

COMMANDS = frozenset({"due", "--cluster", "--retest"})
USAGE = (
    "usage: leetcode due | --cluster <name> [--dry-run] | --retest <slug> [--dry-run]"
)
STAGES = len(progress.RETEST_OFFSETS)
COLD_RETEST_TAG = "[cold re-test]"
COLD_RETEST = (
    f"{COLD_RETEST_TAG} kuhy solved this problem before. This is a cold "
    "re-test: fresh session, no hints or code from last time, requirement "
    "list first as usual. Judge the solution by running the statement's "
    "examples locally with node, not on LeetCode. Tell kuhy: do NOT submit "
    "on LeetCode, a resubmission mints a gate credit."
)

Start = Callable[[list[str]], int]


def accepted_on_leetcode(slug: str) -> bool:
    """Whether LeetCode confirms an Accepted submission; False if it cannot say."""
    try:
        evidence = check_solved(build_client().post, [slug])
    except Exception:  # pylint: disable=broad-exception-caught
        _logger.exception("live solved-check for %s raised; serving it", slug)
        return False
    return slug in evidence.solved


def _due() -> int:
    rows = progress.due_retests()
    if not rows:
        print("no re-tests due")
        return 0
    for row in rows:
        print(
            f"{row['due']}  {row['slug']}  re-test {row['stage']}/{STAGES}  "
            f"({row['cluster'] or 'no cluster'})  ->  leetcode --retest {row['slug']}"
        )
    return 0


def _retest(slug: str, start: Start, *, dry: bool) -> int:
    past = progress.history(slug)
    if past.solved is None:
        print(
            f"{slug} is not solved yet (no code + post-mortem logged)", file=sys.stderr
        )
        return 1
    if past.retests >= STAGES:
        print(f"both re-tests of {slug} are done; practise it with `leetcode {slug}`")
        return 0
    stage = past.retests + 1
    print(f"cold re-test {stage}/{STAGES}: {slug} (solved {past.solved})")
    if dry:
        return 0
    cluster = progress.cluster_of(slug)
    if cluster is None:
        os.environ.pop(progress.CLUSTER_ENV, None)
    else:
        os.environ[progress.CLUSTER_ENV] = cluster
    before = progress.count_events(slug, "postmortem")
    code = start([slug, COLD_RETEST])
    if progress.count_events(slug, "postmortem") > before:
        event = {"event": "retest", "stage": stage, "cluster": cluster}
        progress.append_event(slug, event)
        print(f"re-test {stage}/{STAGES} logged for {slug}")
    else:
        print(
            f"re-test not logged: the session ended without a post-mortem; "
            f"rerun `leetcode --retest {slug}`"
        )
    return code


def _cluster(
    name: str, start: Start, accepted: Callable[[str], bool], *, dry: bool
) -> int:
    clusters = progress.load_clusters()
    if name not in clusters:
        known = ", ".join(clusters)
        print(f"unknown cluster {name!r}; known: {known}", file=sys.stderr)
        return 1
    due = [row for row in progress.due_retests() if row["cluster"] == name]
    if due:
        print(f"re-test due: {due[0]['slug']} (due {due[0]['due']})")
        return _retest(due[0]["slug"], start, dry=dry)
    slug = progress.next_new(name, None, accepted)
    if slug is None:
        print(f"{name}: every problem is started or accepted on LeetCode")
        return 0
    number = next(p["id"] for p in clusters[name] if p["slug"] == slug)
    print(f"next in {name}: {slug} (#{number})")
    if dry:
        return 0
    os.environ[progress.CLUSTER_ENV] = name
    return start([slug])


def main(
    argv: list[str], start: Start, accepted: Callable[[str], bool] | None = None
) -> int:
    """Dispatch `due`, `--cluster <name>` and `--retest <slug>`."""
    dry = "--dry-run" in argv
    args = [a for a in argv if a != "--dry-run"]
    match args:
        case ["due"]:
            return _due()
        case ["--cluster", name]:
            check = accepted_on_leetcode if accepted is None else accepted
            return _cluster(name, start, check, dry=dry)
        case ["--retest", slug]:
            return _retest(slug, start, dry=dry)
        case _:
            print(USAGE, file=sys.stderr)
            return 1
