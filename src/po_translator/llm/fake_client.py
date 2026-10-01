"""Mock/Fake LLM client for integration and testing without actual API calls."""

from __future__ import annotations

import json
from collections.abc import Callable

from po_translator.llm.models import LLMClient, LLMRequest, LLMResponse


class FakeLLMClient(LLMClient):
    """Configurable fake LLM client for testing pipelines, error cases, and validations."""

    def __init__(
        self,
        default_handler: Callable[[LLMRequest], str] | None = None,
    ) -> None:
        self.default_handler = default_handler
        self.call_history: list[LLMRequest] = []
        self.canned_responses: list[str | Exception] = []

    def queue_response(self, response_or_exception: str | Exception) -> None:
        """Queue a predetermined response string or exception for subsequent calls."""
        self.canned_responses.append(response_or_exception)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.call_history.append(request)

        # 1. Pop from canned response queue if available
        if self.canned_responses:
            item = self.canned_responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return LLMResponse(
                content=item,
                model="fake-model",
                prompt_tokens=10,
                completion_tokens=20,
            )

        # 2. Use custom handler if provided
        if self.default_handler:
            content = self.default_handler(request)
            return LLMResponse(
                content=content,
                model="fake-model",
                prompt_tokens=10,
                completion_tokens=20,
            )

        # 3. Default fallback: echo structured translation if it looks like a batch request
        # Attempt to see if messages contain {"entries": [...]}
        for msg in reversed(request.messages):
            try:
                data = json.loads(msg.content)
                if "entries" in data and isinstance(data["entries"], list):
                    trans = [
                        {"id": e["id"], "translation": f"Translated: {e.get('text', '')}"}
                        for e in data["entries"]
                    ]
                    return LLMResponse(
                        content=json.dumps({"translations": trans}, ensure_ascii=False),
                        model="fake-model",
                        prompt_tokens=10,
                        completion_tokens=20,
                    )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass

        return LLMResponse(
            content='{"message": "pong"}',
            model="fake-model",
            prompt_tokens=5,
            completion_tokens=5,
        )
