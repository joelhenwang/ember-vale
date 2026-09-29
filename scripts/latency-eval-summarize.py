"""Summarize latency-eval arm results into a per-arm/per-role table.

Usage: python scripts/latency-eval-summarize.py docs/evidence/latency-eval-001
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
}


def summarize(doc: dict) -> dict:
    rows = {}
    for r in doc["results"]:
        role = r["role"]
        row = rows.setdefault(role, {
            "n": 0, "usable": 0, "exhausted": 0, "provider_error": 0,
            "ttuv": [], "repairs": 0, "reasoning_only": 0, "empty": 0,
            "prompt_tok": 0, "compl_tok": 0, "reason_tok": 0,
        })
        row["n"] += 1
        row[{"usable": "usable", "exhausted": "exhausted"}.get(r["outcome"], "provider_error")] += 1
        if r.get("ttuv_ms", -1) >= 0:
            row["ttuv"].append(r["ttuv_ms"])
        row["repairs"] += r.get("repairs", 0)
        for a in r.get("attempts", []):
            if a.get("reasoning_only"):
                row["reasoning_only"] += 1
            if a.get("error") is None and (a.get("content_len") or 0) == 0:
                row["empty"] += 1
            row["prompt_tok"] += a.get("prompt_tokens", 0)
            row["compl_tok"] += a.get("completion_tokens", 0)
            row["reason_tok"] += a.get("reasoning_tokens", 0)
    return rows


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
            ttuv = row["ttuv"]
            p50 = statistics.median(ttuv) / 1000 if ttuv else float("nan")
            p90 = sorted(ttuv)[max(0, int(len(ttuv) * 0.9) - 1)] / 1000 if ttuv else float("nan")
            est = (row["prompt_tok"] * pp + row["compl_tok"] * pc) / 1e6
            print(
                f"  {role:20s} n={row['n']} usable={row['usable']} "
                f"exhausted={row['exhausted']} provider_err={row['provider_error']} "
                f"ttuv_p50={p50:.1f}s p90={p90:.1f}s repairs={row['repairs']} "
                f"reason_only={row['reasoning_only']} empty={row['empty']} "
                f"tok={row['prompt_tok'] + row['compl_tok']}(+{row['reason_tok']}r) "
                f"est=${est:.4f}"
            )
        print()


if __name__ == "__main__":
    main()
