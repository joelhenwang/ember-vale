"""Evidence-output routing for simulation tests (owned by S0-QA-001).

Gate and soak tests regenerate committed bundles under ``evidence/``.
Serial runs keep writing those bundles in place (regeneration is the
tests' job); two knobs keep that safe:

* ``WORLDSIM_EVIDENCE_DIR`` relocates the bundle root (e.g. a scratch
  directory) without touching tracked paths.
* Under ``pytest -n`` each worker gets a suffixed bundle so parallel
  gates never share one directory.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


def evidence_dir(bundle: str) -> Path:
    """Bundle directory for one evidence-producing test module."""
    root = Path(os.environ.get("WORLDSIM_EVIDENCE_DIR", REPO_ROOT / "evidence"))
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker:
        return root / f"{bundle}-{worker}"
    return root / bundle
