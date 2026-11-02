"""The one-line notes kuhy reads from the phase gate: req list or output shape."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_coach import leak, shape

if TYPE_CHECKING:
    from leetcode_coach.req_check import Check
    from leetcode_coach.toolbox import Toolbox


def property_line(prop: str, box: Toolbox) -> str:
    """`prop: meaning`, or just `prop` when the meaning names an entry.

    Some meanings illustrate with the operation itself (self-inverse:
    "a ^ x ^ x = a"); shown to kuhy that is the answer, not a property.
    """
    meaning = box.properties[prop]
    return prop if leak.leaked_names(meaning, [], box) else f"{prop}: {meaning}"


def _forced(what: str, result: Check) -> str:
    missing = ", ".join(result.missing)
    return f"[{what} still incomplete ({missing}) -- code accepted anyway]"


def req_note(
    result: Check, tries: int, *, forced: bool, limit: int, box: Toolbox
) -> str:
    if result.via == shape.VIA:
        return shape_note(result, tries, forced=forced, limit=limit)
    if result.verdict == "pass":
        return "[req list accepted -- code is open]"
    if result.verdict == "unverified":
        return "[req check unavailable -- continuing unverified, code is open]"
    if forced:
        return _forced("req list", result)
    props = "\n".join(f"  - {property_line(p, box)}" for p in result.missing)
    return (
        f"[req list incomplete -- it does not yet say these properties:\n{props}\n"
        f" revise with req: ({tries} of {limit})]"
    )


def shape_note(result: Check, tries: int, *, forced: bool, limit: int) -> str:
    if result.verdict == "pass":
        return "[output shape accepted -- code is open]"
    if forced:
        return _forced("output shape", result)
    lines = "\n".join(f"  - {h}" for h in shape.hints(result.missing))
    return (
        f"[output shape incomplete -- it does not yet say:\n{lines}\n"
        f" revise with shape: ({tries} of {limit})]"
    )


def refusal(tries: int, limit: int, *, sql: bool) -> str:
    if not tries:
        if sql:
            return (
                "[code held back: state the output shape first -- one message "
                "starting with shape: that says the columns, the rows and the "
                "grouping]"
            )
        return (
            "[code held back: write the requirement list first -- one message "
            "starting with req: that lists the properties the operation must "
            "have, without naming an operation or structure]"
        )
    gate = "output shape" if sql else "req list"
    return (
        f"[code held back: the {gate} is still incomplete -- revise it "
        f"with {'shape' if sql else 'req'}: ({tries} of {limit} so far)]"
    )
