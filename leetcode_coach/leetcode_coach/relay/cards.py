"""Step 5's reward: the post-mortem's property cards, from the answer key.

The existing builder, in-process: property -> operation cards for the key's
toolbox entries (`toolbox_cards.cards_for`), checked by `card_rules` and
delivered by `make_cards.deliver` (AnkiConnect, else an .apkg). The relay
appends the ``postmortem`` event itself: ``make_cards.main`` finds the log
through ``os.environ``, which one process serving many sessions never sets.
A card failure only fills ``error``; the step stays passed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

from leetcode_coach import card_rules, make_cards, toolbox_cards

if TYPE_CHECKING:
    from leetcode_coach.relay.session import Session

_logger: Final = logging.getLogger(__name__)


def build(
    session: Session, entries: tuple[str, ...], *, dry_run: bool = False
) -> dict[str, Any]:
    """Build and deliver the cards; ``{"built", "deck", "error"}``."""
    out: dict[str, Any] = {"built": 0, "deck": make_cards.DECK_NAME, "error": None}
    try:
        cards = toolbox_cards.cards_for(list(entries))
    except (KeyError, OSError, ValueError) as exc:
        _logger.warning("no cards for %s: %s", session.slug, exc)
        return {**out, "error": f"no cards: {exc}"}
    if errors := card_rules.validate(toolbox_cards.SLUG, cards):
        _logger.warning("cards rejected for %s: %s", session.slug, errors)
        return {**out, "error": "cards rejected: " + "; ".join(errors)}
    if dry_run:
        return {**out, "built": len(cards)}
    try:
        line = make_cards.deliver(toolbox_cards.SLUG, cards)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # AnkiConnect, genanki and the disk all fail in their own ways; none
        # of them may cost kuhy the passed step.
        _logger.exception("card delivery failed for %s", session.slug)
        return {**out, "error": f"delivery failed: {exc}"}
    _logger.info("cards for %s: %s", session.slug, line)
    session.log_event("postmortem", cards=len(cards))
    return {**out, "built": len(cards)}
