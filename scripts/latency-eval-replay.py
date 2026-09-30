"""Latency eval replay: frozen captured prompts, one variable per arm ($2 cap).

Arms: A=deepseek baseline, B=GLM model swap, C=temp 0.0, D1=narrator JSON mode.
D1 runs narrator items only (other roles already use json_mode=True live).

Zero-paid-call dry run: --dry-run replays canned valid payloads through the
real adapters/validators with no network.

Results: docs/evidence/latency-eval-001/results-<arm>.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend" / "src"))

from pydantic import SecretStr
from worldsim.application.graphs import (
    character,
    director,
    narrate,
    reaction,
    resolve,
)
from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    ModelGatewayError,
    ModelProfile,
    ModelRateLimitedError,
)
from worldsim.infrastructure.model_gateway.openrouter import (
    OpenRouterGateway,
)

ARMS = {
    "A": {"model": "deepseek/deepseek-v4-flash-0731", "temperature": 0.2, "json_narrator": False},
    "B": {"model": "z-ai/glm-4.7-flash", "temperature": 0.2, "json_narrator": False},
    "C": {"model": "deepseek/deepseek-v4-flash-0731", "temperature": 0.0, "json_narrator": False},
    "D1": {"model": "deepseek/deepseek-v4-flash-0731", "temperature": 0.2, "json_narrator": True},
    "E": {"model": "mistralai/mistral-nemo", "temperature": 0.2, "json_narrator": False},
    "F": {"model": "mistralai/mistral-nemo", "temperature": 0.2, "json_narrator": False,
          "dedupe_prompt_lines": True, "reaction_speakers": True},
}

ROLE_SYSTEM = {
    "narrator": lambda: narrate.render_system_prompt(narrate.load_narrator_prompt()),
    "director": lambda: director.load_director_prompt(),
    "character_decision": lambda: character.render_system_prompt(character.load_character_prompt()),
    "reaction": lambda: reaction.render_system_prompt(reaction.load_reaction_prompt()),
    "resolver": lambda: resolve.render_system_prompt(resolve.load_resolver_prompt()),
}

def narrator_context(user_prompt: str) -> tuple[frozenset[str], frozenset[str], int]:
    """Shared narration-context parser (both documented prompt formats)."""
    return narrate.parse_narration_context(user_prompt)


def dedupe_prompt_lines(prompt: str) -> str:
    """Shared pipeline-equivalent prompt-line dedup."""
    return narrate.dedupe_prompt_lines(prompt)


def validate(
    role: str,
    raw: str,
    user_prompt: str,
    speakers: dict[str, str] | None = None,
) -> tuple[bool, str]:
    """Schema (+ narrator attribution) validation. Returns (ok, detail)."""
    try:
        if role == "narrator":
            proposals = narrate._BEATS_ADAPTER.validate_json(narrate.unfence_json(raw))
            audience, keys, budget = narrator_context(user_prompt)
            denial = narrate.beats_valid(
                proposals, visible_keys=keys, audience_ids=audience,
                beats_budget=budget, fact_speakers=speakers,
            )
            if denial is not None:
                return False, f"beats_valid: {denial}"
            return True, f"{len(proposals)} beats"
        if role == "director":
            proposal = director._PROPOSAL_ADAPTER.validate_json(raw)
            return True, type(proposal).__name__
        if role == "resolver":
            proposal = resolve._PROPOSAL_ADAPTER.validate_json(raw)
            return True, type(proposal).__name__
        if role in ("character_decision", "reaction"):
            adapter = character._ACTION_ADAPTER if role == "character_decision" else reaction._ACTION_ADAPTER
            action = adapter.validate_json(raw)
            return True, type(action).__name__
    except Exception as exc:  # noqa: BLE001 - record any validation failure
        return False, f"{type(exc).__name__}: {str(exc)[:300]}"
    return False, f"unknown role {role}"


CANNED = {
    "narrator": '[{"text": "dry run beat", "cited_fact_keys": ["k"], "kind": "narration"}]',
    "director": '{"plan": "dry"}',
    "resolver": '{"resolution": "dry"}',
    "character_decision": '{"action": "wait"}',
    "reaction": '{"action": "wait"}',
}


class FakeGateway:
    profile = ModelProfile(name="dry", version="dry", adapter="fake", model_id="dry")

    async def complete(self, request: CompletionRequest):
        from worldsim.application.ports.model_gateway import CompletionResult

        return CompletionResult(
            text=CANNED_BY_ROLE[request_role_hint],
            prompt_tokens=len(request.prompt) // 4,
            completion_tokens=10,
            model="dry",
            profile_version="dry",
            latency_ms=1,
        )


def load_key() -> str:
    for line in (REPO / ".env").read_text().splitlines():
        if line.startswith("WORLDSIM_PROVIDER__OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("gateway key missing from .env")


async def run_item(
    gateway,
    arm: str,
    role: str,
    item: dict,
    timeout_s: float,
    speakers: dict[str, str] | None = None,
) -> dict:
    cfg = ARMS[arm]
    system = ROLE_SYSTEM[role]()
    json_mode = True if role != "narrator" else cfg["json_narrator"]
    temp = cfg["temperature"]
    base = item["prompt"]
    if cfg.get("dedupe_prompt_lines"):
        base = dedupe_prompt_lines(base)
    out: dict = {
        "role": role, "prompt_hash": item["prompt_hash"], "arm": arm,
        "attempts": [], "repairs": 0, "validated": False,
        "prompt_deduped": base != item["prompt"],
    }
    ttuv_start = time.monotonic()
    prompt = base
    denial: str | None = None
    for attempt in range(2):  # initial + one repair
        if attempt == 1:
            if role == "narrator":
                prompt = (
                    f"{base}\n\nYour previous output was rejected "
                    f"({denial}). Output a JSON array of beat objects "
                    "matching the response schema."
                )
            else:
                prompt = (
                    f"{base}\n\nYour previous output was rejected "
                    f"({denial}). Output corrected JSON only."
                )
            out["repairs"] = 1
        req = CompletionRequest(
            prompt=prompt, system=system, max_tokens=item["max_tokens"],
            json_mode=json_mode, temperature=temp,
        )
        t0 = time.monotonic()
        try:
            res = await gateway.complete(req)
        except ModelRateLimitedError as exc:
            wait = getattr(exc, "retry_after_s", None) or 5.0
            wait = min(float(wait), 60.0)
            out["attempts"].append({
                "error": "rate_limited", "latency_ms": int((time.monotonic() - t0) * 1000),
                "wait_s": wait,
            })
            await asyncio.sleep(wait)
            try:
                res = await gateway.complete(req)
            except ModelGatewayError as exc2:
                out["attempts"].append({
                    "error": type(exc2).__name__,
                    "detail": str(getattr(exc2, "detail", ""))[:500],
                    "latency_ms": int((time.monotonic() - t0) * 1000),
                })
                break
        except ModelGatewayError as exc:
            detail = getattr(exc, "detail", "")
            if isinstance(detail, dict):
                detail_s = json.dumps(detail)[:2000]
            else:
                detail_s = str(detail)[:2000]
            attempt = {
                "error": type(exc).__name__,
                "detail": detail_s,
                "reasoning_only": bool(isinstance(detail, dict) and detail.get("reasoning_only")),
                "latency_ms": int((time.monotonic() - t0) * 1000),
            }
            # Recover billable usage at capture time; the summarizer still
            # treats unparseable details as usage_missing.
            try:
                usage = (json.loads(detail_s).get("usage") or {}) if detail_s.startswith("{") else {}
                attempt["prompt_tokens"] = int(usage.get("prompt_tokens") or 0)
                attempt["completion_tokens"] = int(usage.get("completion_tokens") or 0)
                attempt["reasoning_tokens"] = int(usage.get("reasoning_tokens") or 0)
            except (ValueError, AttributeError):
                pass
            out["attempts"].append(attempt)
            break
        ok, info = validate(role, res.text, base, speakers)
        out["attempts"].append({
            "latency_ms": res.latency_ms,
            "finish_reason": res.finish_reason,
            "content_len": len(res.text),
            "prompt_tokens": res.prompt_tokens,
            "completion_tokens": res.completion_tokens,
            "reasoning_tokens": res.reasoning_tokens,
            "model": res.model,
            "valid": ok,
            "validation": info,
        })
        out.setdefault("texts", []).append(res.text[:4000])
        if ok:
            out["validated"] = True
            break
        denial = info
    out["ttuv_ms"] = int((time.monotonic() - ttuv_start) * 1000)
    out["outcome"] = (
        "usable" if out["validated"]
        else ("provider_error" if any("error" in a for a in out["attempts"]) else "exhausted")
    )
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=sorted(ARMS))
    ap.add_argument("--fixture", default="docs/evidence/latency-eval-001/fixture.json")
    ap.add_argument("--timeout-s", type=float, default=180.0)
    ap.add_argument("--token-tripwire", type=int, default=400000)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    global request_role_hint, CANNED_BY_ROLE
    fixture = json.loads((REPO / args.fixture).read_text())
    items = fixture["items"]
    if args.arm in ("D1", "E", "F"):
        items = [i for i in items if i["role"] == "narrator"]
    speaker_map: dict[str, dict[str, str]] = {}
    if ARMS[args.arm].get("reaction_speakers"):
        raw_map = json.loads(
            (REPO / "docs/evidence/latency-eval-001/speaker-map.json").read_text())
        for h, m in raw_map.items():
            speaker_map[h] = {k: v for k, v in m["speakers"].items()
                              if k.startswith("reaction:")}
    if args.limit:
        items = items[: args.limit]

    started_wall = time.time()
    if args.dry_run:
        gateway = FakeGateway()  # type: ignore[assignment]
    else:
        profile = ModelProfile(
            name="latency-eval", version="001", adapter="openrouter",
            model_id=ARMS[args.arm]["model"],
        )
        gateway = OpenRouterGateway(
            profile, api_key=SecretStr(load_key()), timeout_s=args.timeout_s,
        )
    results = []
    total_tokens = 0
    consecutive_timeouts = 0
    for i, item in enumerate(items):
        request_role_hint = item["role"]
        CANNED_BY_ROLE = {item["role"]: CANNED[item["role"]]}
        try:
            res = await run_item(
                gateway, args.arm, item["role"], item, args.timeout_s,
                speaker_map.get(item["prompt_hash"]),
            )
        except Exception as exc:  # noqa: BLE001 - harness must not die mid-arm
            res = {"role": item["role"], "prompt_hash": item["prompt_hash"],
                   "arm": args.arm, "outcome": f"harness_error: {type(exc).__name__}",
                   "attempts": [], "repairs": 0, "validated": False, "ttuv_ms": -1}
        for a in res.get("attempts", []):
            # Billable tokens only. Reasoning-token/completion-token overlap is
            # unestablished (observed reasoning > completion), so reasoning
            # tokens are recorded per attempt but never added here.
            total_tokens += a.get("prompt_tokens", 0) + a.get("completion_tokens", 0)
        results.append(res)
        print(f"[{i + 1}/{len(items)}] {item['role']} {item['prompt_hash'][:8]} "
              f"{res['outcome']} ttuv={res.get('ttuv_ms')}ms tokens={total_tokens}", flush=True)
        if any(a.get("error") == "ModelTimeoutError" for a in res.get("attempts", [])):
            consecutive_timeouts += 1
        else:
            consecutive_timeouts = 0
        if consecutive_timeouts >= 3:
            print(f"TIMEOUT-STALL: 3 consecutive timeouts, aborting arm {args.arm}")
            break
        if total_tokens >= args.token_tripwire:
            print(f"TRIPWIRE: {total_tokens} tokens, aborting arm {args.arm}")
            break
    import hashlib

    fixture_bytes = (REPO / args.fixture).read_bytes()
    doc = {
        "arm": args.arm, "config": ARMS[args.arm],
        "fixture_sha": hashlib.sha256(fixture_bytes).hexdigest(),
        "started_wall": started_wall, "ended_wall": time.time(),
        "total_tokens": total_tokens, "dry_run": args.dry_run,
        "results": results,
    }
    out_path = REPO / f"docs/evidence/latency-eval-001/results-{args.arm}.json"
    out_path.write_text(json.dumps(doc, indent=1))
    print(f"wrote {out_path} n={len(results)} tokens={total_tokens}")


if __name__ == "__main__":
    asyncio.run(main())
