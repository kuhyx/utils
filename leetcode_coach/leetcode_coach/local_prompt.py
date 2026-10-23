"""What the offline coach tells the local model, and the one-task shape check.

Split out of `local_coach.py` for the 250-line cap; texts are unchanged.
"""

from __future__ import annotations

import re

WITHHELD = (
    "(My draft gave away code, so I held it back.) Let's go one step smaller: "
    "in your own words, what does your current approach do with each number "
    "as it reads it?"
)
REMINDER = (
    "\n\n[coach reminder, not from kuhy: one hint rung at most; never state "
    "the key insight, the data structure or the fix; never answer your own "
    "question; no code with the starter's names; end with exactly one "
    "question or one instruction.]"
)
"""Appended to the newest user message for the model only -- never stored in
`history` and never seen by the gate. A 3B-active model follows the rules at
the top of a 3k-token system prompt far less reliably than a line next to the
question it is answering (measured on the eval: it named the fix in prose)."""
LOCAL_NOTES = """
## Local client notes (you are running offline, not in Claude Code)

- You have NO tools. The problem statement and starter code are already below;
  never say you will fetch, run or test anything.
- Write plain markdown for a terminal. No emoji.
- Never write code that uses the starter's function or parameter names unless
  kuhy has typed `reveal`. A client-side gate rejects such replies.
- Never name the data structure or algorithm that solves the problem before
  rung H3 -- not even inside a calibration question. Ask about what kuhy
  already said instead.
- The LAST line of every reply is exactly one question or one instruction for
  kuhy. Nothing after it. ONE question mark in the whole closing paragraph:
  never stack questions ("What happens? Why?").
- Never state the key insight, the fix, or what the code "must" do. On a buggy
  paste, describe what the data does on one concrete input from the examples
  ("with [3,2,4] and target 6, at i=0 `seen` already holds 3 when the lookup
  runs") and ask what that lookup returns. kuhy names the fix, not you.
- When kuhy gives up or begs for the answer, do not just point at `reveal`:
  drop back one rung and end with a smaller question. You may mention once
  that typing `reveal` ends the exercise.
- Never repeat a previous reply. Answer what kuhy just wrote.
- For the post-mortem cards (section 5b), do NOT print a Bash command. Emit one
  fenced block tagged `cards` naming the toolbox entries, e.g.
  ```cards
  {"toolbox": ["<entry name>", "<entry name>"]}
  ```
  The client builds the property cards and shows the result. Never append to
  the toolbox from this client: tell kuhy to do it in a Claude session.

# The problem (already fetched)

"""
GATE_REASON_CODE = (
    "leetcode gate: your reply hands kuhy code they can paste -- {snippets}. "
    "Rewrite it without that snippet: describe the data or "
    "name the construct, and keep the one question at the end."
)
GATE_REASON_SHAPE = (
    "leetcode gate: end with exactly ONE question or ONE "
    "instruction -- your closing paragraph asks more than one "
    "thing or ends on neither. Rewrite it."
)
IMPERATIVE = re.compile(
    r"^(try|write|predict|explain|tell|describe|trace|run|paste|list|sketch|"
    r"walk|show|give|say|name|work|think|check|change|fix|look|answer|type|"
    r"fill|pick|do)\b",
    re.IGNORECASE,
)


def system_prompt(skill_md: str, statement: str) -> str:
    """SKILL.md minus frontmatter, fetch step and model gate, plus the problem."""
    body = skill_md.split("\n---\n", 1)[1] if skill_md.startswith("---") else skill_md
    body = re.sub(r"## 1\. Fetch the problem.*?(?=\n## 2\.)", "", body, flags=re.DOTALL)
    body = body.split("\n## Model and client", 1)[0]
    return body.strip() + "\n" + LOCAL_NOTES + statement.strip() + "\n"


def ends_with_one_task(text: str) -> bool:
    """Closing paragraph asks at most one question and ends on a task.

    The task is the final sentence: a question, or an imperative ("Predict
    before I tell you."). A question followed by the instruction to answer it
    is still one task; two question marks are two. Code blocks are not prose,
    and a quoted question ("has this been seen?") is not a second question.
    """
    prose = re.sub(r"```.*?```", "\n\n", text, flags=re.DOTALL)
    paras = [p.strip() for p in re.split(r"\n\s*\n", prose) if p.strip()]
    if not paras:
        return False
    last = re.sub(r"\"[^\"]*\"|“[^”]*”", "it", paras[-1])
    last = re.sub(r"[*_>`()]", "", last).strip()
    if last.count("?") > 1:
        return False
    sentences = [x for x in re.split(r"(?<=[.?!])\s+", last) if x.strip()]
    final = sentences[-1].strip()
    return final.endswith("?") or bool(IMPERATIVE.match(final))
