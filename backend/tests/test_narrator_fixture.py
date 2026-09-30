"""Narrator eval inputs built through production assembly (zero model spend).

Advances a deterministic two-participant scene with scripted gateways and
captures the narrator CompletionRequests production actually built:
sourced observations, deduped facts, current templates, full validation
enforced. The narrator voices an attempt as dialogue, so production must
deny it (speaker attribution after eligibility succeeds) and fall back —
while the captured initial prompt is byte-exact current-pipeline input
for future eval arms.

Writes docs/evidence/latency-eval-001/fixture-narrator-v2.json.
"""
import asyncio
import json
from pathlib import Path
from uuid import UUID

from test_stage1_orchestration import (
    _agency_gateways,
    _orchestrator,
    _seed,
    _set_grant,
    _wren_ask,
)

from worldsim.application.graphs.narrate import parse_narration_context
from worldsim.application.ports.model_gateway import CompletionRequest

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "evidence"
    / "latency-eval-001"
    / "fixture-narrator-v2.json"
)


def _request_record(request: CompletionRequest) -> dict:
    return {
        "prompt": request.prompt,
        "system": request.system,
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "top_k": request.top_k,
        "json_mode": request.json_mode,
    }


def test_production_assembly_builds_deduped_narrator_prompt(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        gateways = _agency_gateways(ids)

        def _speakerless_dialogue(request: CompletionRequest) -> str | None:
            _audience, keys, _budget = parse_narration_context(request.prompt)
            speech = sorted(k for k in keys if k.startswith("reaction:"))
            if not speech:
                raise AssertionError("fixture scene must commit quoted speech")
            return json.dumps(
                [
                    {
                        "text": "Dawn patrol passed at first light.",
                        "cited_fact_keys": [speech[0]],
                        "kind": "dialogue",
                        "speaker_id": None,
                    }
                ]
            )

        gateways["narrator"].route = _speakerless_dialogue
        report = await _orchestrator(gateways).advance_phase(ids["world"], 1, _wren_ask(ids))
        assert not report.duplicate
        assert all(s.narration == "fallback" for s in report.scenes)

        requests = gateways["narrator"].sent_requests
        assert len(requests) == 2  # initial + one bounded repair
        initial = requests[0]
        lines = initial.prompt.splitlines()
        fact_lines = [line for line in lines if line.startswith("- ")]
        assert fact_lines
        assert len(fact_lines) == len(set(fact_lines)), "observer copies deduplicated"
        assert all(
            line.startswith('- key "') or line.startswith("- ") and "(id:" in line
            for line in fact_lines
        ), "current quoted-key fact format with speaker roster"
        audience, keys, budget = parse_narration_context(initial.prompt)
        assert len(audience) == 2
        assert all(UUID(a) for a in audience)
        assert keys
        assert budget >= 1

        FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE_PATH.write_text(
            json.dumps(
                {
                    "source": "production assembly (narrator fixture test)",
                    "model": None,
                    "items": [_request_record(initial)],
                },
                indent=1,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    asyncio.run(_inner())
