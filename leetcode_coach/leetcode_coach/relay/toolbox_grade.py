"""Step 3, the toolbox pick, graded mechanically against the answer key.

No model. Key entries `K` (``entries``), picks `P`. An entry in
``also_accepted`` is a correct alternative: each one picked stands in for
one key entry not picked (sum instead of XOR for Missing Number). A combined
key entry ("prefix sum + hash map") also counts as picked when every one of
its parts is: each part must resolve to another toolbox entry by name or
alias, ignoring case and a plural ``s`` ("prefix sum" -> "prefix sums"); a
part that names no entry ("merge") means only the combined entry counts.

* pass: every key entry is covered (picked, built from its parts, or stood
  in for) and at most one pick is neither key, part nor alternative;
* partial: something right was picked, but not that;
* fail: nothing right was picked.

Feedback is the properties the uncovered key entries need that no pick has,
as property names (`phase.property_line`), never an entry name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from leetcode_coach import phase

if TYPE_CHECKING:
    from leetcode_coach.answer_key import Answer
    from leetcode_coach.toolbox import Entry, Toolbox

MAX_EXTRAS: Final = 1
MIN_PARTS: Final = 2
SPREAD: Final = (
    "Your picks have the properties, but spread over tools that do not "
    "combine; find the tool that has them together."
)
TOO_MANY: Final = "Fewer picks: more than one of these is not needed."


def _key(text: str) -> str:
    return " ".join(text.split()).casefold()


def resolve(name: str, box: Toolbox) -> Entry | None:
    """The entry called `name` (or with that alias)."""
    wanted = _key(name)
    return next(
        (e for e in box.entries if wanted in {_key(n) for n in e.names()}), None
    )


def parts(entry: Entry, box: Toolbox) -> tuple[Entry, ...] | None:
    """The entries a combined ``a + b`` entry is made of; None if not all exist."""
    pieces = [p.strip() for p in entry.name.split(" + ")]
    if len(pieces) < MIN_PARTS:  # a plain entry has no parts
        return None
    found: list[Entry] = []
    for piece in pieces:
        match = resolve(piece, box) or resolve(piece + "s", box)
        if match is None or match.name == entry.name:
            return None
        found.append(match)
    return tuple(found)


def grade(picks: list[str], key: Answer, box: Toolbox) -> tuple[str, str]:
    """``(grade, feedback)`` for `picks` (entry names, already resolvable)."""
    chosen = {e.name for p in picks if (e := resolve(p, box)) is not None}
    used: set[str] = set()
    missing: list[str] = []
    for name in key.entries:
        entry = resolve(name, box)
        made = None if entry is None else parts(entry, box)
        if name in chosen:
            used.add(name)
        elif made is not None and all(m.name in chosen for m in made):
            used.update(m.name for m in made)
        else:
            missing.append(name)
    stand_ins = chosen & set(key.also_accepted)
    extras = chosen - used - stand_ins
    if len(missing) <= len(stand_ins) and len(extras) <= MAX_EXTRAS:
        return "pass", ""
    verdict = "partial" if used or stand_ins else "fail"
    return verdict, _feedback(missing, chosen, extras, box)


def _feedback(
    missing: list[str], chosen: set[str], extras: set[str], box: Toolbox
) -> str:
    have = {p for e in box.entries if e.name in chosen for p in e.properties}
    need: list[str] = []
    for name in missing:
        entry = resolve(name, box)
        for prop in () if entry is None else entry.properties:
            if prop not in have and prop not in need:
                need.append(prop)
    lines = [f"- {phase.property_line(p, box)}" for p in need if p in box.properties]
    if lines:
        head = "The operation you need also has these properties, which no pick has:"
        text = "\n".join([head, *lines])
    else:
        text = SPREAD if missing else ""
    if len(extras) > MAX_EXTRAS:
        text = f"{text}\n{TOO_MANY}".strip()
    return text
