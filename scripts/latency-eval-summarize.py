"""Summarize latency-eval arm results (corrected: TTUV split, failed-call usage).

- elapsed_to_terminal: wall ms per item over ALL outcomes (success + failure).
- ttuv_validated: wall ms over PASSED items only, with denominator (N/A if 0).
- passed: items passing the replay checks (scope below), NOT "usable".
- cost: prompt+completion tokens x catalog price. Reasoning tokens are
  reported separately; whether they overlap completion is unestablished, so
  they are never costed and never added to completion.
- failed-call usage is recovered from retained diag detail strings; calls
  whose detail lacks parseable usage are counted as usage_missing.

Validation scope: schema-parse for all roles; narrator additionally runs
beats_valid with audience/keys/budget parsed from the prompt, with
fact_speakers=None (speaker-to-source check disabled).

Zero spend: reads result JSON only.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

PRICE = {
    "deepseek/deepseek-v4-flash-0731": (0.021, 0.32),
    "z-ai/glm-4.7-flash": (0.0605, 0.40),
    "mistralai/mistral-nemo": (0.019, 0.03),
}


def detail_usage(detail: str) -> tuple[dict, bool]:
    try:
        payload = json.loads(detail)
    except ValueError:
        return {}, False
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return {}, False
    return usage, True


def summarize(doc: dict) -> dict:
    rows = {}
    for r in doc["results"]:
        row = rows.setdefault(r["role"], {
            "n": 0, "passed": 0, "exhausted": 0, "provider_error": 0,
            "terminal_ms": [], "validated_ms": [], "repairs": 0,
            "reasoning_only": 0, "empty": 0,
            "ok_prompt": 0, "ok_compl": 0, "ok_reason": 0,
            "fail_prompt": 0, "fail_compl": 0, "fail_reason": 0,
            "usage_missing": 0,
        })
        row["n"] += 1
        if r.get("ttuv_ms", -1) >= 0:
            row["terminal_ms"].append(r["ttuv_ms"])
        if r.get("validated"):
            row["passed"] += 1
            if r.get("ttuv_ms", -1) >= 0:
                row["validated_ms"].append(r["ttuv_ms"])
        elif r.get("outcome") == "exhausted":
            row["exhausted"] += 1
        else:
            row["provider_error"] += 1
        row["repairs"] += r.get("repairs", 0)
        for a in r.get("attempts", []):
            if a.get("reasoning_only"):
                row["reasoning_only"] += 1
            if a.get("error") is None and (a.get("content_len") or 0) == 0:
                row["empty"] += 1
            if a.get("error") is None:
                row["ok_prompt"] += a.get("prompt_tokens", 0)
                row["ok_compl"] += a.get("completion_tokens", 0)
                row["ok_reason"] += a.get("reasoning_tokens", 0)
            else:
                usage, found = detail_usage(a.get("detail") or "")
                if found:
                    row["fail_prompt"] += usage.get("prompt_tokens", 0) or 0
                    row["fail_compl"] += usage.get("completion_tokens", 0) or 0
                    row["fail_reason"] += usage.get("reasoning_tokens", 0) or 0
                else:
                    row["usage_missing"] += 1
    return rows


def pct50(vals: list) -> str:
    return f"{statistics.median(vals) / 1000:.1f}s" if vals else "N/A"


def pct90(vals: list) -> str:
    if not vals:
        return "N/A"
    return f"{sorted(vals)[max(0, int(len(vals) * 0.9) - 1)] / 1000:.1f}s"


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/evidence/latency-eval-001")
    for path in sorted(root.glob("results-*.json")):
        doc = json.loads(path.read_text())
        if doc.get("dry_run"):
            continue
        model = doc["config"]["model"]
        pp, pc = PRICE.get(model, (0.0, 0.0))
        print(f"== arm {doc['arm']} model={model} temp={doc['config']['temperature']} "
              f"json_narrator={doc['config']['json_narrator']} ==")
        for role, row in summarize(doc).items():
            est = ((row["ok_prompt"] + row["fail_prompt"]) * pp
                   + (row["ok_compl"] + row["fail_compl"]) * pc) / 1e6
            print(
                f"  {role:20s} n={row['n']} passed={row['passed']} "
                f"exhausted={row['exhausted']} provider_err={row['provider_error']} "
                f"terminal[{pct50(row['terminal_ms'])}/{pct90(row['terminal_ms'])}] "
                f"validated[{pct50(row['validated_ms'])}/{pct90(row['validated_ms'])}]"
                f"(n={len(row['validated_ms'])}) repairs={row['repairs']} "
                f"reason_only={row['reasoning_only']} empty={row['empty']} "
                f"tok_ok={row['ok_prompt'] + row['ok_compl']}(+{row['ok_reason']}r) "
                f"tok_fail={row['fail_prompt'] + row['fail_compl']}(+{row['fail_reason']}r) "
                f"missing={row['usage_missing']} est=${est:.4f}"
            )
        print()


if __name__ == "__main__":
    main()
