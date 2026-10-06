"""One-time export of embeddinggemma to OpenVINO IR with int8 weights.

    uv run --extra export python -m local_models.export

Uses the ungated unsloth mirror of google/embeddinggemma-300m (same
weights, Gemma licence; the Google repo needs a manual access grant).
int8 matched full precision (cosine 1.000, top-5 agreement 0.97) and
was five times faster; int4 lost quality for no speed, so it is not
offered here.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = "unsloth/embeddinggemma-300m"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=SOURCE)
    parser.add_argument("--out", type=Path, default=ROOT / "models" / "embeddinggemma-300m-int8")
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    command = [
        shutil.which("optimum-cli", path=str(Path(sys.executable).parent)) or "optimum-cli",
        "export", "openvino",
        "--model", args.model,
        "--library", "sentence_transformers",
        "--task", "feature-extraction",
        "--weight-format", "int8",
        str(args.out),
    ]  # fmt: skip
    subprocess.run(command, check=True)
    print(f"exported to {args.out}")


if __name__ == "__main__":
    main()
