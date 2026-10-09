"""Live A/B of the narrator's D&D rules: dnd-rules.v2 vs v3 on the same code.

For each version: serve the API (the branch's code, a scratch database, the
provider the repo .env selects; only WORLDSIM_PROVIDER__* lines are read
from .env), run party-combat-001/live_check.py RUNS times (a new combat
story, three "attack the goblin" turns each), and count the dice the engine
rolled. Prints one JSON summary.

  python rules_ab.py <repo> <worktree> <scratch-db-url> [runs]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO, WORKTREE, DB_URL = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
RUNS = int(sys.argv[4]) if len(sys.argv) > 4 else 3
PORT = "8103"
PY = str(REPO / "backend" / ".venv" / "Scripts" / "python.exe")


def env_lines(prefix: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix) and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip().strip('"')
    return out


key = env_lines("WORLDSIM_SECURITY__API_KEY")["WORLDSIM_SECURITY__API_KEY"]
summary: dict[str, list[dict[str, object]]] = {}
for version in ("dnd-rules.v2", "dnd-rules.v3"):
    env = {
        **{k: v for k, v in os.environ.items() if not k.startswith("WORLDSIM_")},
        **env_lines("WORLDSIM_PROVIDER__"),
        "WORLDSIM_DATABASE__URL": DB_URL,
        "WORLDSIM_SECURITY__API_KEY": key,
        "WORLDSIM_AUTOPLAY__ENABLED": "false",
        "RULES_VERSION": version,
        "PORT": PORT,
        "PYTHONPATH": str(WORKTREE / "backend" / "src"),
    }
    server = subprocess.Popen(
        [PY, str(Path(__file__).with_name("serve_rules.py"))],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(120):
            try:
                if httpx.get(f"http://localhost:{PORT}/api/v1/health/live").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        runs = []
        for _ in range(RUNS):
            done = subprocess.run(
                [PY, str(REPO / "docs/evidence/party-combat-001/live_check.py"), f"http://localhost:{PORT}", key],
                capture_output=True,
                text=True,
                timeout=900,
            )
            result = json.loads(done.stdout)
            runs.append(
                {
                    "rolls": len(result["rolls"]),
                    "roll_lines": result["rolls"],
                    "tags_in_prose": result["tags_in_prose"],
                    "foes": result["foes"],
                    "turn_status": [t["status"] for t in result["turns"]],
                }
            )
        summary[version] = runs
    finally:
        server.terminate()
        server.wait(timeout=30)
print(json.dumps(summary, indent=1))
