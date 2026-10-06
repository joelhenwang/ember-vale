# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""NarrationGraph: post-commit narration beats (owned by S1-NARRATE-001).

START -> validate post-commit gating -> render audience-scoped context
-> call narrator model -> validate beats against visible facts
-> repair once on unsupported facts -> structured-event fallback -> END.

Beats are linked presentation data: they cite committed fact keys and
source event IDs, never establish facts. The graph never touches
projections or repositories; the worker persists returned beats and
acks the narration outbox record. A missing or failed narrator falls
back to structured event text; canon never waits for prose.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from langgraph.graph import StateGraph
from pydantic import TypeAdapter, ValidationError

from worldsim.application.graphs.state import GraphState
from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    ModelGateway,
    ModelMalformedError,
    ModelProfile,
    ModelRateLimitedError,
    ModelRefusalError,
    ModelTimeoutError,
    ModelUnavailableError,
    unfence_json,
)
from worldsim.domain.commands import CommunicateAction, MoveAction
from worldsim.domain.enums import NarrationKind, ReactionStatus
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_narration_id
from worldsim.domain.narration import BeatProposal, NarrationBeat
from worldsim.domain.rules.repeats import overlap
from worldsim.domain.scenes import Intent, Reaction

#: Versioned narrator prompt file.
NARRATOR_PROMPT_VERSION = "narrator.v3"
#: What the audience last saw of these people: continuity, never news.
RECAP_FACT_KEY = "previously"
#: Facts that set the scene rather than report an event (no fallback beat).
SETTING_FACT_KEYS = frozenset({"place", "pronouns", RECAP_FACT_KEY})

_BEATS_ADAPTER: TypeAdapter[list[BeatProposal]] = TypeAdapter(list[BeatProposal])


class NarrateState(GraphState, total=False):
    """Graph state plus narration-local gating and prompt fields."""

    event_id: str
    event_committed: bool
    audience_ids: list[str]
    visible_facts: list[dict[str, str]]
    beats_budget: int
    dnd_context: str | None
    system_prompt: str
    user_prompt: str
    raw_response: str | None


@dataclass(frozen=True)
class NarratorGraphDeps:
    """Everything the graph may call: a gateway and static text."""

    gateway: ModelGateway
    profile: ModelProfile
    system_template: str
    max_tokens: int = 512
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    repair_budget: int = 1


def prompt_path() -> Path:
    """Versioned prompt file next to the backend root."""
    return Path(__file__).resolve().parents[4] / "prompts" / f"{NARRATOR_PROMPT_VERSION}.md"


def load_narrator_prompt() -> str:
    """Read the versioned narrator prompt (fails loudly when missing)."""
    return prompt_path().read_text(encoding="utf-8")


def render_system_prompt(template: str) -> str:
    """Fill the response-schema placeholder (the only placeholder)."""
    schema_json = json.dumps(_BEATS_ADAPTER.json_schema(), indent=2, sort_keys=True)
    return template.replace("{{RESPONSE_SCHEMA}}", schema_json)


def _fact_view(raw: Any) -> dict[str, str]:
    """Prompt/validation view of one visible fact, keeping attribution."""
    view = {"key": str(raw["key"]), "value": str(raw["value"])}
    speaker = raw.get("speaker")
    if speaker:
        view["speaker"] = str(speaker)
    utterance = raw.get("utterance")
    if utterance:
        view["utterance"] = str(utterance)
    speaker_name = raw.get("speaker_name")
    if speaker_name:
        view["speaker_name"] = str(speaker_name)
    pronouns = raw.get("speaker_pronouns")
    if pronouns:
        view["speaker_pronouns"] = str(pronouns)
    return view


def _speaker_roster(visible_facts: list[dict[str, str]]) -> list[str]:
    """Authoritative speaker name-to-ID mapping lines for the narrator.

    The validator checks speaker_id against the same source; without the
    mapping rendered, the model cannot comply.
    """
    seen: set[str] = set()
    entries: list[str] = []
    for fact in visible_facts:
        speaker = fact.get("speaker")
        name = fact.get("speaker_name")
        if speaker and name and speaker not in seen:
            seen.add(speaker)
            pronouns = fact.get("speaker_pronouns")
            stated = f"{pronouns}, " if pronouns else ""
            entries.append(f"- {name} ({stated}id: {speaker})")
    if not entries:
        return []
    return ["Speakers (use these exact ids when setting speaker_id):", *entries]


_AUDIENCE_RE = re.compile(r"^Audience:\s*(.*)$", re.M)
_KEY_RE = re.compile(r'^-\s*key\s+"([^"]+)"\s*:', re.M)
_LEGACY_KEY_RE = re.compile(r"^- ([A-Za-z0-9_:.\-]+):\s", re.M)
_PROMPT_BUDGET_RE = re.compile(r"^Beat budget:\s*(\d+)\s*\.\s*$", re.M)


def dedupe_prompt_lines(prompt: str) -> str:
    """Drop repeated `- ` fact lines, keeping first occurrences.

    HISTORICAL-EXPERIMENT ONLY (arm F replay). Identical lines do NOT
    imply identical (source, key) facts in general: distinct actions can
    render identical text, and production correctly preserves those via
    source IDs. Build future integration fixtures through production
    assembly/rendering with source identities preserved.
    """
    seen: set[str] = set()
    kept: list[str] = []
    for line in prompt.splitlines():
        if line.startswith("- ") and line in seen:
            continue
        seen.add(line)
        kept.append(line)
    return "\n".join(kept)


def parse_narration_context(user_prompt: str) -> tuple[frozenset[str], frozenset[str], int]:
    """Invert render_user_prompt audience/fact rendering, both known formats.

    The renderer ends the audience line with a sentence period that is not
    part of any id, and historical prompts render facts as `- key:` without
    quotes. Roster lines (`- Name (id: ...)`) never match either pattern.
    """
    audience: set[str] = set()
    m = _AUDIENCE_RE.search(user_prompt)
    if m:
        rendered = m.group(1).strip()
        if rendered.endswith("."):
            rendered = rendered[:-1]
        audience = {a.strip() for a in rendered.split(",") if a.strip() and a.strip() != "none"}
    keys = set(_KEY_RE.findall(user_prompt)) | set(_LEGACY_KEY_RE.findall(user_prompt))
    b = _PROMPT_BUDGET_RE.search(user_prompt)
    return frozenset(audience), frozenset(keys), int(b.group(1)) if b else 8


_ATTEMPT_SPEECH_RE = re.compile(r"^(.*?) says to (.*?): (.*)$", re.DOTALL)


def citation_aliases(facts: list[dict[str, str]]) -> dict[str, str]:
    """Short prompt labels for long citation keys: real key -> alias.

    Reaction and speech keys embed a 36-character UUID next to speaker
    UUIDs, which invites a model to cite ``reaction:<speaker id>``. Each is
    shown as ``reaction:1``, ``speech:1`` ... per prefix in fact order; the graph
    maps cited aliases back before validation, so stored beats, canon and
    audit rows keep the real keys. Other keys are already short.
    """
    aliases: dict[str, str] = {}
    counts: dict[str, int] = {}
    for fact in facts:
        key = str(fact["key"])
        prefix = key.split(":", 1)[0]
        if prefix in ("reaction", "speech") and key not in aliases:
            counts[prefix] = counts.get(prefix, 0) + 1
            aliases[key] = f"{prefix}:{counts[prefix]}"
    return aliases


def shown_denial(denial: str, aliases: Mapping[str, str]) -> str:
    """Denial text as the model saw the keys (real keys -> aliases)."""
    for key, alias in aliases.items():
        denial = denial.replace(key, alias)
    return denial


def resolve_citations(
    proposals: list[BeatProposal], aliases: Mapping[str, str]
) -> list[BeatProposal]:
    """Map aliased citations back to real keys; unknown keys pass through
    unchanged so the validator still rejects them."""
    real = {alias: key for key, alias in aliases.items()}
    return [
        p.model_copy(update={"cited_fact_keys": [real.get(k, k) for k in p.cited_fact_keys]})
        for p in proposals
    ]


def _render_fact_line(fact: Mapping[str, str], shown_key: str | None = None) -> str:
    """One prompt line with its source category stated explicitly.

    Attempts are narration-only by construction: communicate attempts read
    as attempts with a topic, never as quoted speech. Committed quoted
    speech carries its speaker id and dialogue eligibility inline;
    attributed summaries are marked narration-only. Stored fact values are
    untouched — this is presentation only, so canon and history keep
    their wording.
    """
    key = str(fact["key"])
    value = str(fact["value"])
    speaker = fact.get("speaker")
    shown = shown_key or key
    if key.startswith("attempt:"):
        match = _ATTEMPT_SPEECH_RE.match(value) if "communicate" in key else None
        if match:
            text = (
                f"{match.group(1)} attempts to communicate with {match.group(2)}; "
                f"topic: {match.group(3)}"
            )
        else:
            text = value
        return f'- key "{shown}": [attempt \u2014 narration-only] {text}'
    if speaker and fact.get("utterance"):
        name = fact.get("speaker_name", speaker)
        return (
            f'- key "{shown}": [quoted speech \u2014 dialogue-eligible] {value} '
            f"(speaker {name}, id: {speaker})"
        )
    if speaker:
        return f'- key "{shown}": [attributed summary \u2014 narration-only] {value}'
    if key == RECAP_FACT_KEY:
        return f'- key "{shown}": [recap \u2014 already seen; continuity only] {value}'
    return f'- key "{shown}": {value}'


#: 128 cut off one live narration in forty at the cap (p90 used 825 of 1024).
NARRATOR_TOKENS_PER_BEAT = 192
TRUNCATED_DENIAL = "output truncated at the token limit"


def narrator_max_tokens(configured: int, beats_budget: int) -> int:
    """Completion cap that can hold the whole beat budget.

    The sampling profile's max_tokens is shared by every role; a full
    narration of 8 JSON beats needs roughly 500 tokens, so a 512 cap
    truncates busy events mid-JSON. Never below the configured value,
    never above the gateway ceiling of 4096.
    """
    floor = NARRATOR_TOKENS_PER_BEAT * max(beats_budget, 1)
    return min(max(configured, floor), 4096)


def schema_denial(error_count: int, finish_reason: str | None) -> str:
    """Denial for unparsable output; truncation gets its own correction."""
    if finish_reason == "length":
        return TRUNCATED_DENIAL
    return f"{error_count} schema errors"


def repair_instruction(denial: str) -> str:
    """Actionable repair suffix shared by production and the eval replay.

    The guidance follows the denial: non-speech dialogue must become
    narrator prose or be removed; eligible speech with a missing or wrong
    speaker keeps its utterance under the source's exact speaker; schema,
    citation, and budget failures get the corresponding correction without
    any claim about dialogue.
    """
    head = f"Your previous output was rejected ({denial}). "
    tail = "Output a JSON array of beat objects matching the response schema."
    if TRUNCATED_DENIAL in denial:
        fix = (
            "The output hit the length limit before the JSON array closed. "
            "Write fewer, shorter beats: one beat per quoted utterance, "
            "attempts summarized together, and no fact narrated twice. "
        )
    elif "dialogue cites non-speech evidence" in denial:
        fix = (
            "The cited beat is invalid as dialogue: rewrite it as factual "
            "narrator prose with speaker_id null citing the same key, or "
            "remove it. Do not fix this by citing a different speech key "
            "— never put words in a speaker's mouth that the cited "
            "utterance does not support; "
            "quote identified utterances faithfully. "
        )
    elif "dialogue requires a speaker matching cited speech" in denial:
        fix = (
            "Keep the beat as dialogue with its supported utterance, but set "
            "speaker_id to the cited speech fact's exact speaker. "
        )
    elif (
        "speaker does not match cited source" in denial or "speaker outside the audience" in denial
    ):
        fix = (
            "Fix the speaker attribution without changing what the evidence "
            "supports: for dialogue supported by eligible speech, set "
            "speaker_id to the cited speech fact's exact speaker with its "
            "supported utterance — never leave it null and never borrow "
            "another voice. For narrator prose, retain narration and use "
            "speaker_id: null. Never convert narration-only evidence into "
            "dialogue to fix attribution. "
        )
    elif "unsupported facts cited" in denial or "must cite at least one" in denial:
        fix = (
            "Cite only visible fact keys exactly as quoted after `key`; drop "
            "or replace any invented or missing key instead of keeping it. "
        )
    elif "beat budget exceeded" in denial or "at least one beat" in denial:
        fix = "Keep the narration within the beat budget with at least one beat. "
    elif "does not quote cited speech" in denial:
        fix = (
            "Quote the cited words exactly in the dialogue beat, or rewrite "
            "the beat as narrator prose. Do not change the speaker or the "
            "key to work around the mismatch. "
        )
    elif "schema errors" in denial:
        fix = (
            "Emit a single JSON array of beat objects exactly matching the "
            "response schema, with no surrounding prose or fencing. "
        )
    else:
        fix = "Correct exactly the stated problem and resubmit valid beats. "
    return head + fix + tail


def render_user_prompt(
    audience_ids: list[str],
    visible_facts: list[dict[str, str]],
    event_id: str,
    scene_id: str | None,
    beats_budget: int,
    dnd_context: str | None = None,
) -> str:
    """Audience-scoped context: facts, event linkage, and beat budget.

    Reaction keys are shown by their citation_aliases label."""
    aliases = citation_aliases(visible_facts)
    lines = [
        f"Event {event_id}" + (f" in scene {scene_id}." if scene_id else "."),
        f"Audience: {', '.join(audience_ids) or 'none'}.",
        "Visible facts:",
        *[_render_fact_line(fact, aliases.get(str(fact["key"]))) for fact in visible_facts],
        *_speaker_roster(visible_facts),
        f"Beat budget: {beats_budget}.",
    ]
    if dnd_context:
        lines.append(dnd_context)
    return "\n".join(lines)


def _identify_utterance(topic: str) -> str | None:
    """Explicitly identified spoken words from a communication topic.

    Data contract: a communication ``topic`` is an about-topic unless the
    model marks direct speech explicitly by wrapping it in matching
    quotation marks. Only a quoted topic counts as an identified utterance;
    everything else is paraphrased by attributed narrative summaries, never
    quoted as spoken words.
    """
    text = topic.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        inner = text[1:-1].strip()
        return inner or None
    return None


_QUOTE_TRANSLATE = str.maketrans(
    {
        chr(8220): chr(34),
        chr(8221): chr(34),
        chr(8216): chr(39),
        chr(8219): chr(39),
        chr(8217): chr(39),
    }
)
_TRAILING_PUNCT = ".,!?;:"


def _normalize_quote(text: str) -> str:
    """Comparable form for quote containment: curly quotes unified,
    double quote marks dropped (stray inner quotes in a stored utterance
    must not force a fallback), whitespace runs collapsed, trailing
    punctuation stripped. Apostrophes are kept as part of words."""
    unified = str(text).translate(_QUOTE_TRANSLATE).replace('"', " ")
    return " ".join(unified.split()).rstrip(_TRAILING_PUNCT)


def communication_facts(
    reactions: list[Reaction],
    names: Mapping[UUID, str],
    audience_ids: list[str] | frozenset[str],
) -> list[dict[str, str]]:
    """Visible facts for committed communications (speech or summary).

    One fact per committed ``communicate`` reaction whose speaker and
    target are both in the audience. The citation key derives from the
    stable reaction ID, so concurrent speakers never collide. Rejected
    proposals never reach this input: only committed rows are read, and
    the reaction carries no hidden rationale. A topic counts as quoted
    utterance only when explicitly identified; see _identify_utterance.
    """
    audience = frozenset(str(a) for a in audience_ids)
    facts: list[dict[str, str]] = []
    for reaction in reactions:
        if reaction.status != ReactionStatus.COMMITTED:
            continue
        action = reaction.action
        if not isinstance(action, CommunicateAction):
            continue
        speaker = reaction.reactor_character_id
        target = action.target_character_id
        if str(speaker) not in audience or str(target) not in audience:
            continue
        topic = action.topic.strip()
        utterance = _identify_utterance(topic)
        if not topic:
            continue
        speaker_name = names.get(speaker, speaker.hex[:8])
        target_name = names.get(target, target.hex[:8])
        if utterance is not None:
            value = f'{speaker_name} says to {target_name}: "{utterance}"'
        else:
            value = f'{speaker_name} speaks to {target_name} about "{topic}"'
        facts.append(
            {
                "key": f"reaction:{reaction.id}",
                "value": value,
                "speaker": str(speaker),
                "speaker_name": speaker_name,
                **({"utterance": utterance} if utterance is not None else {}),
            }
        )
    return facts


def move_note_facts(intents: Sequence[Intent], names: Mapping[UUID, str]) -> list[dict[str, str]]:
    """What a traveller set out to do, in the player's words, for the narrator."""
    facts: list[dict[str, str]] = []
    for intent in intents:
        action = intent.action
        if isinstance(action, MoveAction) and action.note:
            name = names.get(intent.author_character_id, "Someone")
            facts.append(
                {
                    "key": f"move-note:{intent.id}",
                    "value": f"{name} sets out meaning to: {action.note}",
                }
            )
    return facts


def attempt_speech_facts(
    intents: Sequence[Intent],
    names: Mapping[UUID, str],
    audience_ids: list[str] | frozenset[str],
) -> list[dict[str, str]]:
    """Speech facts for communicate attempts whose topic quotes exact words.

    A player's "Say" line (or any attempt that quotes its words) is the
    actor's own speech, so it is dialogue-eligible under the same contract
    as quoted reactions: speaker and target both in the audience, words
    identified only by quotation marks (see _identify_utterance). The
    attempt fact itself stays narration-only; this adds the spoken words
    under a stable ``speech:<intent id>`` key. Unquoted topics add nothing.
    """
    audience = frozenset(str(a) for a in audience_ids)
    facts: list[dict[str, str]] = []
    for intent in intents:
        action = intent.action
        if not isinstance(action, CommunicateAction):
            continue
        utterance = _identify_utterance(action.topic)
        if utterance is None:
            continue
        speaker = intent.author_character_id
        target = action.target_character_id
        if str(speaker) not in audience or str(target) not in audience:
            continue
        speaker_name = names.get(speaker, speaker.hex[:8])
        target_name = names.get(target, target.hex[:8])
        facts.append(
            {
                "key": f"speech:{intent.id}",
                "value": f'{speaker_name} says to {target_name}: "{utterance}"',
                "speaker": str(speaker),
                "speaker_name": speaker_name,
                "utterance": utterance,
            }
        )
    return facts


def speech_eligible_keys(facts: list[dict[str, str]]) -> frozenset[str]:
    """Keys eligible for DIALOGUE citation: committed quoted speech only.

    Attempted communication and unquoted topic summaries carry no identified
    utterance and may only be paraphrased as narration. Same predicate the
    deterministic fallback uses: speaker plus utterance.
    """
    return frozenset(f["key"] for f in facts if f.get("speaker") and f.get("utterance"))


#: A narration sentence sharing this much of a recap sentence's words is a retelling.
RETOLD_OVERLAP = 0.7
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def drop_retold(proposals: list[BeatProposal], recap: str | None) -> list[BeatProposal]:
    """Drop narration sentences that copy the recap, and beats left empty.

    Playtest: a beat opened "The low fire at Hearth still crackles as the
    newcomer, Wren, takes a step forward", nearly word for word the last
    beat's opening, despite the prompt. Dialogue is left alone (quotes are
    checked elsewhere); a narration that would lose every beat keeps all.
    """
    if not recap:
        return proposals
    told = [line for line in _SENTENCE.split(recap.split(": ", 1)[-1]) if line.strip()]
    kept: list[BeatProposal] = []
    for proposal in proposals:
        if proposal.kind == NarrationKind.DIALOGUE:
            kept.append(proposal)
            continue
        fresh = [
            line
            for line in _SENTENCE.split(proposal.text)
            if line.strip() and not any(overlap(line, old) >= RETOLD_OVERLAP for old in told)
        ]
        if fresh:
            kept.append(proposal.model_copy(update={"text": " ".join(fresh)}))
    return kept or proposals


def drop_recap_only(proposals: list[BeatProposal]) -> list[BeatProposal]:
    """Drop beats that only retell the recap, when anything else remains.

    Such a beat narrates the past as if new; dropping it loses nothing and
    spares a repair call (about one narration in sixteen wrote one). A
    narration made only of recap beats is left for the validator to reject.
    """
    kept = [p for p in proposals if set(p.cited_fact_keys) != {RECAP_FACT_KEY}]
    return kept or proposals


def _quotes(text: str, quote: str) -> bool:
    """Whether beat text carries the cited utterance (the validator's own test)."""
    normalized = _normalize_quote(quote)
    return not normalized or bool(
        re.search(r"(?<!\w)" + re.escape(normalized) + r"(?!\w)", _normalize_quote(text))
    )


_QUOTE_MARKS = re.compile(r"[\"“”]")


def soften_dialogue(
    proposals: list[BeatProposal],
    speech_keys: frozenset[str] | None,
    utterances: Mapping[str, str] | None,
    speaker_names: Mapping[str, str] | None = None,
) -> list[BeatProposal]:
    """Repair two common dialogue slips in place instead of asking again.

    A dialogue beat that cites quoted speech plus other facts keeps only
    the speech citations. One that reports its cited speech instead of
    quoting it ("Ash answers that the market is quiet": no quote marks,
    the speaker named) becomes narration, which may paraphrase. Together
    these were half of all narrator repairs. Other words in a speaker's
    mouth, or a dialogue beat citing no speech at all, are left for the
    validator: softening them would invent or misattribute speech.
    """
    if speech_keys is None:
        return proposals
    out: list[BeatProposal] = []
    for proposal in proposals:
        if proposal.kind != NarrationKind.DIALOGUE:
            out.append(proposal)
            continue
        speech = [k for k in proposal.cited_fact_keys if k in speech_keys]
        if not speech:
            out.append(proposal)
            continue
        if len(speech) < len(proposal.cited_fact_keys):
            proposal = proposal.model_copy(update={"cited_fact_keys": speech})
        names = [n for k in speech if (n := (speaker_names or {}).get(k))]
        reported = (
            not _QUOTE_MARKS.search(proposal.text)
            and bool(names)
            and all(n.casefold() in proposal.text.casefold() for n in names)
        )
        if (
            utterances is not None
            and reported
            and not all(_quotes(proposal.text, utterances[k]) for k in speech if k in utterances)
        ):
            proposal = proposal.model_copy(
                update={"kind": NarrationKind.NARRATION, "speaker_id": None}
            )
        out.append(proposal)
    return out


def beats_valid(
    proposals: list[BeatProposal],
    *,
    visible_keys: frozenset[str],
    audience_ids: frozenset[str],
    beats_budget: int,
    fact_speakers: Mapping[str, str] | None = None,
    speech_keys: frozenset[str] | None = None,
    fact_utterances: Mapping[str, str] | None = None,
) -> str | None:
    """Unsupported-fact validator: cited keys, speakers, and budget.

    Beats citing a spoken-communication fact must carry that fact's
    speaker; attribution is checked against the source, not the audience.
    DIALOGUE beats may only cite speech-eligible keys (committed quoted
    speech); attempts and topic summaries are narration-only. None skips
    the speech check (legacy callers). When fact_utterances is given,
    DIALOGUE text must contain the cited quote (whitespace, curly
    quotes, and final punctuation ignored).
    """
    if not proposals:
        return "narration needs at least one beat"
    if len(proposals) > beats_budget:
        return f"beat budget exceeded: {len(proposals)} > {beats_budget}"
    speakers = dict(fact_speakers or {})
    utterances = dict(fact_utterances or {})
    for proposal in proposals:
        unknown = set(proposal.cited_fact_keys) - visible_keys
        if unknown:
            return f"unsupported facts cited: {sorted(unknown)}"
        if not proposal.cited_fact_keys:
            return "every beat must cite at least one visible fact"
        if set(proposal.cited_fact_keys) == {RECAP_FACT_KEY}:
            return "a beat cannot rest on the recap alone: cite what happens now"
        if (
            speech_keys is not None
            and proposal.kind == NarrationKind.DIALOGUE
            and not set(proposal.cited_fact_keys) <= set(speech_keys)
        ):
            ineligible = sorted(set(proposal.cited_fact_keys) - set(speech_keys))
            return f"dialogue cites non-speech evidence: {ineligible}"
        if proposal.kind == NarrationKind.DIALOGUE and proposal.speaker_id is None:
            return "dialogue requires a speaker matching cited speech"
        if proposal.speaker_id is not None and str(proposal.speaker_id) not in audience_ids:
            return f"speaker outside the audience: {proposal.speaker_id}"
        for key in proposal.cited_fact_keys:
            expected = speakers.get(key)
            if (
                expected is not None
                and proposal.speaker_id is not None
                and str(proposal.speaker_id) != expected
            ):
                return f"speaker does not match cited source: {key}"
        if fact_utterances is not None and proposal.kind == NarrationKind.DIALOGUE:
            normalized_text = _normalize_quote(proposal.text)
            for key in proposal.cited_fact_keys:
                quote = utterances.get(key)
                normalized_quote = _normalize_quote(quote) if quote else ""
                if normalized_quote and not re.search(
                    r"(?<!\w)" + re.escape(normalized_quote) + r"(?!\w)",
                    normalized_text,
                ):
                    return f"dialogue does not quote cited speech: {key}"
    return None


def dedupe_narration_facts(
    facts: Sequence[tuple[str, str, UUID | None]],
) -> list[tuple[str, str]]:
    """One narration fact per underlying action.

    Observer copies share (source, key) and collapse to the first copy;
    distinct actions survive even with the same key or identical text,
    and facts without recorded provenance pass through untouched
    (legacy rows). Never dedupe by key alone: one family key covers
    many distinct actions.

    Output order is deterministic (key, then source, then text):
    observations arrive ordered by observer id, which is random per
    world, and prompt order changes model output
    (nemo-006 voiced communicate attempts more often when attempt:wait
    was listed first). Sorting also keeps narrator prompts reproducible.
    """
    ordered = sorted(facts, key=lambda f: (f[0], str(f[2] or ""), f[1]))
    seen: set[tuple[str, str]] = set()
    unique: list[tuple[str, str]] = []
    for key, value, source_id in ordered:
        if source_id is not None:
            marker = (str(source_id), key)
            if marker in seen:
                continue
            seen.add(marker)
        unique.append((key, value))
    return unique


def _normalize_fallback_fact(fact: dict[str, Any]) -> dict[str, Any]:
    """Deterministic attributed fallback shape for one visible fact.

    Identified utterances (speaker plus utterance) become DIALOGUE beats
    with exactly the quoted words; topic summaries keep an attributed
    narrative summary with their speaker. Attempts read as attempts via
    the same parse the prompt uses — never as quoted speech — and beat
    text never shows fact keys; keys live only in cited_fact_keys.
    """
    speaker = fact.get("speaker")
    utterance = fact.get("utterance")
    if speaker and utterance:
        return {
            "key": fact["key"],
            "kind": NarrationKind.DIALOGUE,
            "speaker": UUID(str(speaker)),
            "text": str(utterance),
        }
    if speaker:
        return {
            "key": fact["key"],
            "kind": NarrationKind.NARRATION,
            "speaker": UUID(str(speaker)),
            "text": str(fact["value"]),
        }
    key = str(fact["key"])
    value = str(fact["value"])
    if key.startswith("attempt:"):
        match = _ATTEMPT_SPEECH_RE.match(value) if "communicate" in key else None
        if match:
            value = f"{match.group(1)} tries to speak with {match.group(2)} about: {match.group(3)}"
        return {
            "key": fact["key"],
            "kind": NarrationKind.NARRATION,
            "speaker": None,
            "text": value,
        }
    return {
        "key": fact["key"],
        "kind": NarrationKind.NARRATION,
        "speaker": None,
        "text": value,
    }


def fallback_beats(
    *,
    world_id: UUID,
    scene_id: UUID | None,
    event_id: UUID,
    visible_facts: list[dict[str, str]],
    beats_budget: int,
) -> list[NarrationBeat]:
    """Structured-event fallback: one beat per visible fact, budget-capped.

    Facts keep their original order so attempts (questions) come before
    the reactions (answers) that follow them. When the budget cuts facts
    off, the earliest facts are kept. Setting facts (``place``) frame the
    scene for the model and are not events, so they get no beat here.
    """
    events = [f for f in visible_facts if f.get("key") not in SETTING_FACT_KEYS]
    facts = [_normalize_fallback_fact(f) for f in events[: max(beats_budget, 1)]]
    if not facts:
        return [
            NarrationBeat(
                id=new_narration_id(),
                world_id=world_id,
                scene_id=scene_id,
                source_event_id=event_id,
                kind=NarrationKind.NARRATION,
                text="Nothing of note occurs.",
            )
        ]
    return [
        NarrationBeat(
            id=new_narration_id(),
            world_id=world_id,
            scene_id=scene_id,
            source_event_id=event_id,
            cited_fact_keys=[fact["key"]],
            speaker_id=fact["speaker"],
            kind=fact["kind"],
            text=fact["text"],
        )
        for fact in facts
    ]


def stamp_beats(
    proposals: list[BeatProposal],
    *,
    world_id: UUID,
    scene_id: UUID | None,
    event_id: UUID,
) -> list[NarrationBeat]:
    """Stamp model proposals with ids and committed event linkage."""
    return [
        NarrationBeat(
            id=new_narration_id(),
            world_id=world_id,
            scene_id=scene_id,
            source_event_id=event_id,
            source_effect_ids=list(proposal.source_effect_ids),
            cited_fact_keys=list(proposal.cited_fact_keys),
            speaker_id=proposal.speaker_id,
            kind=proposal.kind,
            text=proposal.text,
            emotion_hint=proposal.emotion_hint,
        )
        for proposal in proposals
    ]


def build_narration_graph(deps: NarratorGraphDeps) -> Any:
    """Compile the post-commit narration graph around injected dependencies."""

    def validate_gating(state: NarrateState) -> dict[str, Any]:
        if state.get("event_committed") is not True:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, "narration starts after event commit")
        event_raw = state.get("event_id")
        if not isinstance(event_raw, str) or not event_raw:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, "narration needs an event")
        return {"status": "gating_valid"}

    def render_prompts(state: NarrateState) -> dict[str, Any]:
        event_raw = state.get("event_id")
        scene_raw = state.get("scene_id")
        audience_raw = state.get("audience_ids")
        facts_raw = state.get("visible_facts")
        budget_raw = state.get("beats_budget")
        assert isinstance(event_raw, str) and event_raw
        assert isinstance(audience_raw, list)
        assert isinstance(facts_raw, list)
        assert isinstance(budget_raw, int) and budget_raw >= 1
        return {
            "system_prompt": render_system_prompt(deps.system_template),
            "user_prompt": render_user_prompt(
                [str(a) for a in audience_raw],
                [_fact_view(f) for f in facts_raw],
                event_raw,
                str(scene_raw) if scene_raw else None,
                budget_raw,
                state.get("dnd_context"),
            ),
        }

    async def decide(state: NarrateState) -> dict[str, Any]:
        system = state.get("system_prompt")
        user = state.get("user_prompt")
        assert isinstance(system, str) and isinstance(user, str)
        world_raw = state.get("world_id")
        event_raw = state.get("event_id")
        scene_raw = state.get("scene_id")
        assert isinstance(world_raw, str) and isinstance(event_raw, str)
        world_id, event_id = UUID(world_raw), UUID(event_raw)
        scene_id = UUID(str(scene_raw)) if scene_raw else None
        facts = [_fact_view(f) for f in state.get("visible_facts", [])]
        visible_keys = frozenset(f["key"] for f in facts)
        audience = frozenset(str(a) for a in state.get("audience_ids", []))
        budget_raw = state.get("beats_budget")
        budget = budget_raw if isinstance(budget_raw, int) else 8
        fact_speakers = {f["key"]: f["speaker"] for f in facts if "speaker" in f}
        speech_keys = speech_eligible_keys(facts)
        fact_utterances = {f["key"]: f["utterance"] for f in facts if "utterance" in f}
        aliases = citation_aliases(facts)
        max_tokens = narrator_max_tokens(deps.max_tokens, budget)
        errors: list[str] = []
        repairs = 0
        try:
            result = await deps.gateway.complete(
                CompletionRequest(
                    prompt=user,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=deps.temperature,
                    top_p=deps.top_p,
                    top_k=deps.top_k,
                )
            )
        except (
            ModelTimeoutError,
            ModelRateLimitedError,
            ModelUnavailableError,
            ModelRefusalError,
            ModelMalformedError,
        ) as exc:
            beats = fallback_beats(
                world_id=world_id,
                scene_id=scene_id,
                event_id=event_id,
                visible_facts=facts,
                beats_budget=budget,
            )
            return _narrated(
                state, beats, True, f"provider failed ({type(exc).__name__})", [], 0, None
            )
        raw: str | None = result.text
        finish_reason = result.finish_reason
        while True:
            try:
                proposals = _BEATS_ADAPTER.validate_json(unfence_json(raw))
            except ValidationError as exc:
                errors.append(
                    f"attempt {repairs}: {schema_denial(exc.error_count(), finish_reason)}"
                )
                if repairs >= deps.repair_budget:
                    return _fallback(
                        state, world_id, scene_id, event_id, facts, budget, errors, repairs, raw
                    )
                repairs += 1
                raw, finish_reason = await _repair_call(deps, system, user, errors[-1], max_tokens)
                if raw is None:
                    return _fallback(
                        state, world_id, scene_id, event_id, facts, budget, errors, repairs, None
                    )
                continue
            proposals = soften_dialogue(
                drop_recap_only(resolve_citations(proposals, aliases)),
                speech_keys,
                fact_utterances,
                {f["key"]: f["speaker_name"] for f in facts if f.get("speaker_name")},
            )
            denial = beats_valid(
                proposals,
                visible_keys=visible_keys,
                audience_ids=audience,
                beats_budget=budget,
                fact_speakers=fact_speakers,
                speech_keys=speech_keys,
                fact_utterances=fact_utterances,
            )
            if denial is not None:
                errors.append(f"attempt {repairs}: {denial}")
                if repairs >= deps.repair_budget:
                    return _fallback(
                        state, world_id, scene_id, event_id, facts, budget, errors, repairs, raw
                    )
                repairs += 1
                raw, finish_reason = await _repair_call(
                    deps, system, user, shown_denial(denial, aliases), max_tokens
                )
                if raw is None:
                    return _fallback(
                        state, world_id, scene_id, event_id, facts, budget, errors, repairs, None
                    )
                continue
            # Party narration carries combat and recruit tags: never trim it.
            party = any(f["key"].startswith("dnd-sheet:") for f in facts)
            recap = next((f["value"] for f in facts if f["key"] == RECAP_FACT_KEY), None)
            if not party:
                proposals = drop_retold(proposals, recap)
            beats = stamp_beats(proposals, world_id=world_id, scene_id=scene_id, event_id=event_id)
            return _narrated(state, beats, False, "valid", errors, repairs, raw)

    builder = StateGraph(NarrateState)
    builder.add_node("validate_gating", validate_gating)
    builder.add_node("render_prompts", render_prompts)
    builder.add_node("decide", decide)
    builder.set_entry_point("validate_gating")
    builder.add_edge("validate_gating", "render_prompts")
    builder.add_edge("render_prompts", "decide")
    builder.set_finish_point("decide")
    return builder.compile()


async def _repair_call(
    deps: NarratorGraphDeps, system: str, user: str, denial: str, max_tokens: int
) -> tuple[str | None, str | None]:
    """One bounded repair call: (text, finish_reason); text None when the provider fails."""
    try:
        repaired = await deps.gateway.complete(
            CompletionRequest(
                prompt=f"{user}\n\n{repair_instruction(denial)}",
                system=system,
                max_tokens=max_tokens,
                temperature=deps.temperature,
                top_p=deps.top_p,
                top_k=deps.top_k,
            )
        )
    except (
        ModelTimeoutError,
        ModelRateLimitedError,
        ModelUnavailableError,
        ModelRefusalError,
        ModelMalformedError,
    ):
        return None, None
    return repaired.text, repaired.finish_reason


def _beats_json(beats: list[NarrationBeat]) -> list[dict[str, Any]]:
    return [b.model_dump(mode="json") for b in beats]


def _narrated(
    state: NarrateState,
    beats: list[NarrationBeat],
    fallback: bool,
    reason: str,
    errors: list[str],
    repairs: int,
    raw: str | None,
) -> dict[str, Any]:
    return {
        "proposal": {
            "beats": _beats_json(beats),
            "fallback": fallback,
            "reason": reason,
        },
        "validation_errors": errors,
        "repair_count": repairs,
        "raw_response": raw,
        "status": "fallback" if fallback else "narrated",
    }


def _fallback(
    state: NarrateState,
    world_id: UUID,
    scene_id: UUID | None,
    event_id: UUID,
    facts: list[dict[str, str]],
    budget: int,
    errors: list[str],
    repairs: int,
    raw: str | None,
) -> dict[str, Any]:
    beats = fallback_beats(
        world_id=world_id,
        scene_id=scene_id,
        event_id=event_id,
        visible_facts=facts,
        beats_budget=budget,
    )
    return _narrated(state, beats, True, "structured-event fallback", errors, repairs, raw)


__all__ = [
    "NARRATOR_PROMPT_VERSION",
    "RECAP_FACT_KEY",
    "NarrateState",
    "NarratorGraphDeps",
    "beats_valid",
    "attempt_speech_facts",
    "build_narration_graph",
    "citation_aliases",
    "dedupe_narration_facts",
    "dedupe_prompt_lines",
    "speech_eligible_keys",
    "fallback_beats",
    "load_narrator_prompt",
    "parse_narration_context",
    "render_user_prompt",
    "narrator_max_tokens",
    "repair_instruction",
    "resolve_citations",
    "schema_denial",
    "shown_denial",
    "stamp_beats",
]
