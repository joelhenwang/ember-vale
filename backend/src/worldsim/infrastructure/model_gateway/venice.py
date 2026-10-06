"""Venice adapter: the OpenAI-compatible client with Venice's own switches.

Venice serves the same /chat/completions shape as OpenRouter, so the
transport, error mapping and usage reading are shared. Two differences:
Venice prepends its own system prompt unless told not to (about 1,200
prompt tokens per call, measured 2026-10-06), and it has no
OpenRouter-style ``reasoning`` field; thinking models take
``venice_parameters.disable_thinking`` instead.
"""

from __future__ import annotations

from typing import Any

from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.infrastructure.model_gateway.openrouter import OpenRouterGateway

VENICE_BASE_URL = "https://api.venice.ai/api/v1"


class VeniceGateway(OpenRouterGateway):
    def _body(self, request: CompletionRequest) -> dict[str, Any]:
        body = super()._body(request)
        body.pop("reasoning", None)
        params: dict[str, Any] = {"include_venice_system_prompt": False}
        if self.reasoning == "off":
            params["disable_thinking"] = True
            params["strip_thinking_response"] = True
        body["venice_parameters"] = params
        return body
