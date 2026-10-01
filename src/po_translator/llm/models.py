"""Pydantic and data models for LLM interaction."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class Message(BaseModel):
    """Chat completion message."""
    role: str  # "system", "user", "assistant"
    content: str


class LLMProfile(BaseModel):
    """Configuration profile for connecting to an OpenAI-compatible LLM service."""
    name: str = "default"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o"
    temperature: float = 0.2
    timeout_seconds: float = 60.0
    rpm: int | None = 60
    max_concurrency: int = 5
    max_retries: int = 3


class LLMRequest(BaseModel):
    """Standardized LLM completion request."""
    system_prompt: str = ""
    messages: list[Message] = Field(default_factory=list)
    temperature: float = 0.2
    response_schema: dict[str, Any] | None = None
    stream: bool = False


class LLMResponse(BaseModel):
    """Standardized LLM completion response."""
    content: str
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    raw: dict[str, Any] | None = None


@runtime_checkable
class LLMClient(Protocol):
    """Protocol defining client interface for LLM completions."""

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Execute a completion request asynchronously."""
        ...
