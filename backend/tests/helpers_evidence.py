"""Evidence-output routing for simulation tests (owned by S0-QA-001).

Gate and soak tests produce evidence bundles. Routine runs write them
to a scratch directory so the tracked ``evidence/`` tree never churns:

* ``WORLDSIM_WRITE_EVIDENCE=1`` regenerates the committed bundles under
  ``evidence/`` in place (deliberate evidence refreshes only).
* ``WORLDSIM_EVIDENCE_DIR`` relocates the bundle root explicitly and
  wins over both defaults.
* Under ``pytest -n`` each worker gets a suffixed bundle so parallel
  gates never share one directory.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


def evidence_dir(bundle: str) -> Path:
    """Bundle directory for one evidence-producing test module."""
    explicit = os.environ.get("WORLDSIM_EVIDENCE_DIR")
    if explicit:
        root = Path(explicit)
    elif os.environ.get("WORLDSIM_WRITE_EVIDENCE") == "1":
        root = REPO_ROOT / "evidence"
    else:
        root = Path(tempfile.gettempdir()) / "worldsim-evidence"
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker:
        return root / f"{bundle}-{worker}"
    return root / bundle
