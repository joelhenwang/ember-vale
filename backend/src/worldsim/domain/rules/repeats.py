"""Repeated questions: what a character already asked and was answered.

Characters re-asked questions that had been answered ("What brings you
to the vale?" four beats running). From a character's own observations
this finds their answered exchanges (a line they said to someone, then
that person's reply to them), and whether a new line repeats one. A
question that was never answered may be asked again: pressing a
put-off question is allowed. Pure and deterministic.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

#: A line counts as a repeat when this share of its words (the shorter
#: line's) were in the earlier one; the scorecard uses the same measure.
REPEAT_OVERLAP = 0.6
#: Or when local embeddings put it this close (calibrated on live lines).
REPEAT_SIMILARITY = 0.85

_WORD = re.compile(r"[A-Za-z']+")
_STOP = frozenset(
    {
        "the", "and", "you", "your", "for", "with", "that", "this", "what", "have",
        "are", "was", "but", "not", "any", "about", "from", "there", "here", "into",
        "can", "let", "lets", "let's", "our", "out", "will", "would", "just", "all",
    }
)  # fmt: skip


@dataclass(frozen=True)
class Exchange:
    """A line a character said to someone, and that person's answer."""

    phase: int
    said: str
    to: str
    answer: str


def words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2 and w not in _STOP}


def overlap(a: str, b: str) -> float:
    """Shared words over the shorter line's words (0 when either is empty)."""
    left, right = words(a), words(b)
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _spoken(value: str, speaker: str) -> tuple[str, str] | None:
    """(listener, words) when ``value`` is ``speaker`` talking to someone."""
    for verb in (" says to ", " replies to "):
        head = f"{speaker}{verb}"
        if value.startswith(head) and ":" in value[len(head) :]:
            listener, _, said = value[len(head) :].partition(":")
            return listener.strip(), said.strip().strip('"').strip()
    return None


def answered_exchanges(
    lines: Sequence[tuple[int, str]], speaker: str, *, limit: int = 6
) -> list[Exchange]:
    """The speaker's latest answered exchanges, newest first.

    ``lines`` are (phase, line) in the order perceived, e.g. "Wren says to
    Ash: What brings you here?" then "Ash replies to Wren: "The fair."".
    """
    found: list[Exchange] = []
    for position, (phase, value) in enumerate(lines):
        mine = _spoken(value, speaker)
        if mine is None:
            continue
        listener, said = mine
        if not said:
            continue
        for later_phase, later in lines[position + 1 :]:
            reply = _spoken(later, listener)
            if reply is not None and reply[0] == speaker and reply[1]:
                found.append(Exchange(phase, said, listener, f"{listener}: {reply[1]}"))
                break
            if later_phase - phase > 2:
                break
    return list(reversed(found))[:limit]


def repeated(
    line: str,
    exchanges: Sequence[Exchange],
    similarity: Mapping[int, float] | None = None,
) -> Exchange | None:
    """The answered exchange a new line repeats, if any.

    ``similarity`` maps an exchange's position to the cosine between its
    line and the new one, when local embeddings are at hand.
    """
    found = repeats(line, exchanges, similarity)
    return found[0] if found else None


def repeats(
    line: str,
    exchanges: Sequence[Exchange],
    similarity: Mapping[int, float] | None = None,
) -> list[Exchange]:
    """Every answered exchange a new line repeats, closest first: more than
    one means the character keeps coming back to the same matter."""
    scored: list[tuple[float, int, Exchange]] = []
    for position, exchange in enumerate(exchanges):
        score = overlap(line, exchange.said)
        cosine = (similarity or {}).get(position, 0.0)
        if score >= REPEAT_OVERLAP or cosine >= REPEAT_SIMILARITY:
            scored.append((max(score, cosine), position, exchange))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [exchange for _score, _position, exchange in scored]


def settled_note(exchanges: Sequence[Exchange]) -> str:
    """Prevention: what was already asked and answered, as a goals line."""
    items = "; ".join(f'you said to {e.to} "{e.said}" and heard {e.answer}' for e in exchanges)
    return f"Already asked and answered (build on these, do not ask again): {items}."


#: Coming back to the same matter this often is a loop: talking is off the
#: table for the turn (watched-party-001: "asking the townsfolk about the
#: empty stalls", agreed and re-agreed eight turns running, never done).
LOOP_TIMES = 2


def retry_note(line: str, exchange: Exchange, times: int = 1) -> str:
    """The check: a pointed note for a second try after a repeat."""
    note = (
        f'You were about to say "{line}", but you already said "{exchange.said}" to '
        f"{exchange.to} and heard {exchange.answer} Say something new, act on what you "
        "heard, or do something else."
    )
    if times >= LOOP_TIMES:
        note += (
            f" You have come back to this {times} times already: talking about it again "
            "changes nothing. This turn, do not talk: do it (go somewhere, try something "
            "with your hands, look around for what you need) or turn to something else."
        )
    return note
