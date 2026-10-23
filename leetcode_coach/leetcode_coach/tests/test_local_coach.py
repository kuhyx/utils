"""Tests for the offline /leetcode coach: prompt, no-solution gate, cards.

No network and no GPU: HTTP, nvidia-smi and subprocesses are stubbed.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

import pytest

from leetcode_coach import local_cards, local_coach, local_prompt, local_session
from leetcode_coach.tests._shared import LEAK, SAFE, STATEMENT, FakeChat, completed

if TYPE_CHECKING:
    import subprocess


def _coach(*texts: str) -> tuple[local_coach.LocalCoach, FakeChat]:
    fake = FakeChat(*texts)
    coach = local_coach.LocalCoach.start(STATEMENT)
    coach.chat = fake
    return coach, fake


def test_system_prompt_drops_fetch_step_and_model_gate() -> None:
    skill = (local_coach.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    prompt = local_prompt.system_prompt(skill, STATEMENT)
    assert "fetch_problem.py" not in prompt
    assert "/model sonnet" not in prompt
    assert "## 3. Requirements first, then the hint ladder" in prompt
    assert "<!-- rung:H0 -->" in prompt
    assert prompt.rstrip().endswith("```")
    assert "var twoSum" in prompt


def test_system_prompt_without_frontmatter_keeps_the_body() -> None:
    prompt = local_prompt.system_prompt("# body only", "stmt")
    assert prompt.startswith("# body only\n")
    assert prompt.endswith("stmt\n")


def test_gate_blocks_starter_identifiers_but_allows_quoting_kuhy() -> None:
    assert local_coach.gate_findings(LEAK, STATEMENT, ["hi"])
    paste = "for (const n of nums) seen.set(target - n, n)"
    assert not local_coach.gate_findings(LEAK, STATEMENT, [paste])
    assert not local_coach.gate_findings(LEAK, STATEMENT, ["reveal"])
    assert not local_coach.gate_findings(LEAK, "no starter here", ["hi"])


def test_leaky_reply_is_regenerated_with_the_gate_reason() -> None:
    coach, fake = _coach(LEAK, SAFE)
    turn = coach.respond("just give me the code")
    assert turn.text == SAFE
    assert turn.attempts == 2
    assert "leetcode gate" in fake.prompts[1][-1]["content"]
    assert coach.history[-1] == {"role": "assistant", "content": SAFE}
    assert all("leetcode gate" not in m["content"] for m in coach.history)


def test_three_leaks_withhold_the_reply() -> None:
    coach, _ = _coach(LEAK, LEAK, LEAK)
    turn = coach.respond("code pls")
    assert turn.withheld
    assert turn.text == local_prompt.WITHHELD
    assert "nums" not in turn.text


def test_prior_history_is_kept_for_a_mid_session_fallback() -> None:
    prior = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    coach = local_coach.LocalCoach.start(STATEMENT, prior)
    assert coach.history[1:] == prior


def test_split_cards_extracts_json_and_flags_garbage() -> None:
    text = 'Done.\n```cards\n{"slug": "two-sum", "cards": []}\n```\n'
    assert local_cards.split_cards(text) == ("Done.", {"slug": "two-sum", "cards": []})
    assert local_cards.split_cards("plain") == ("plain", None)
    _, bad = local_cards.split_cards("```cards\nnot json\n```")
    assert bad is not None
    assert "invalid" in bad
    _, arr = local_cards.split_cards("```cards\n[1]\n```")
    assert arr == {"invalid": [1]}


def test_deliver_cards_pipes_to_make_cards() -> None:
    seen: dict[str, Any] = {}

    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        seen.update(cmd=cmd, input=kw["input"])
        return completed(0, "| table |")

    ok, out = local_cards.deliver_cards({"slug": "s", "cards": []}, run=run)
    assert ok
    assert out == "| table |"
    assert seen["cmd"] == [sys.executable, "-m", "leetcode_coach.make_cards", "-"]
    assert json.loads(seen["input"]) == {"slug": "s", "cards": []}
    assert local_cards.deliver_cards({"invalid": "x"})[0] is False


def test_rejected_cards_are_fed_back_once_fixed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cards = '```cards\n{"slug": "s", "cards": []}\n```'
    coach, _ = _coach("fixed\n" + cards)
    results = iter([(False, "cards rejected: back too long"), (True, "| ok |")])
    monkeypatch.setattr(local_cards, "deliver_cards", lambda _p: next(results))
    local_session.show(local_coach.Turn("bye\n" + cards, 1.0, 1, withheld=False), coach)
    out = capsys.readouterr().out
    assert out == "bye\ncards rejected: back too long\n\n...\nfixed\n| ok |\n"
    assert "rejected" in coach.user_texts()[-1]


def test_rejected_cards_give_up_after_the_retries(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cards = '```cards\n{"slug": "s", "cards": []}\n```'
    # The last failed delivery still asks for a fix that is never shown: that
    # is how the skill behaved before the move, kept as-is.
    coach, fake = _coach("again\n" + cards, "still\n" + cards, "last\n" + cards)
    monkeypatch.setattr(local_cards, "deliver_cards", lambda _p: (False, "no"))
    local_session.show(local_coach.Turn("bye\n" + cards, 1.0, 1, withheld=False), coach)
    out = capsys.readouterr().out
    assert out.count("no\n") == local_session.CARD_RETRIES + 1
    assert "last" not in out
    assert fake.texts == []


def test_stacked_questions_are_regenerated_then_shown_if_stuck() -> None:
    coach, fake = _coach("What? Why?", SAFE)
    turn = coach.respond("hint")
    assert (turn.text, turn.attempts) == (SAFE, 2)
    assert "exactly ONE question" in fake.prompts[1][-1]["content"]
    coach, _ = _coach("What? Why?", "How? When?", "Who? Where?")
    turn = coach.respond("hint")
    assert not turn.withheld
    assert turn.text == "Who? Where?"


def test_a_cards_reply_needs_no_closing_question() -> None:
    reply = 'Done.\n```cards\n{"slug": "s", "cards": []}\n```'
    coach, _ = _coach(reply)
    assert coach.respond("bye").text == reply


def test_reminder_reaches_the_model_but_not_history() -> None:
    coach, fake = _coach(SAFE)
    coach.respond("hint")
    assert fake.prompts[0][-1]["content"].endswith(local_prompt.REMINDER)
    assert coach.history[-2] == {"role": "user", "content": "hint"}


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ('What lets you check "has this been seen?" fast?', True),
        ("Try:\n```js\nx?.y\n```\nWhat prints? Predict before I tell you.", True),
        ("Answer in one word.", True),
        ("What happens? Why?", False),
        ("Nice work.", False),
        ("", False),
    ],
)
def test_eval_one_task_checker(text: str, *, ok: bool) -> None:
    assert local_prompt.ends_with_one_task(text) is ok
