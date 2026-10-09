"""Serve the API with the D&D story rules version from RULES_VERSION (A/B check)."""
import os
import sys

from worldsim.domain.rules.dnd import party

party.STORY_RULES_PROMPT_VERSION = os.environ["RULES_VERSION"]
from worldsim.interfaces.cli import main  # noqa: E402

sys.exit(main(["serve", "--port", os.environ.get("PORT", "8103")]))
