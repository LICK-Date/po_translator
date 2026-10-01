"""OpenAI-compatible asynchronous LLM client."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

from po_translator.exceptions import (
    LLMAuthenticationError,
    LLMError,
    LLMNetworkError,
    LLMRateLimitError,
    LLMResponseError,
)
from po_translator.llm.models import LLMProfile, LLMRequest, LLMResponse
from po_translator.llm.rate_limiter import AsyncRateLimiter

logger = logging.getLogger(__name__)


class OpenAICompatibleClient:
    """Async client adhering to OpenAI chat completions protocol with rate-limiting and retries."""

    def __init__(self, profile: LLMProfile) -> None:
        self.profile = profile
        self.rate_limiter = AsyncRateLimiter(
            rpm=profile.rpm,
            max_concurrency=profile.max_concurrency,
        )

    def _normalize_endpoint(self) -> str:
        """Ensure endpoint ends cleanly with /chat/completions."""
        base = self.profile.base_url.rstrip("/")
        if not base.endswith("/chat/completions"):
            return f"{base}/chat/completions"
        return base

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.profile.api_key:
            headers["Authorization"] = f"Bearer {self.profile.api_key.strip()}"
        return headers

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send chat completion request with rate limiting and exponential backoff retries."""
        url = self._normalize_endpoint()
        headers = self._build_headers()

        # Build payload messages
        messages_payload: list[dict[str, str]] = []
        if request.system_prompt:
            messages_payload.append({"role": "system", "content": request.system_prompt})

        for msg in request.messages:
            messages_payload.append({"role": msg.role, "content": msg.content})

        payload: dict[str, Any] = {
            "model": self.profile.model,
            "messages": messages_payload,
            "temperature": request.temperature,
        }

        if request.response_schema:
            payload["response_format"] = {"type": "json_object"}

        timeout = httpx.Timeout(self.profile.timeout_seconds)
        max_retries = max(0, self.profile.max_retries)
        last_exception: Exception | None = None

        for attempt in range(max_retries + 1):
            async with self.rate_limiter:
                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        resp = await client.post(url, json=payload, headers=headers)

                    # Handle authentication failure immediately without retrying
                    if resp.status_code in (401, 403):
                        raise LLMAuthenticationError(
                            f"LLM authentication failed with status {resp.status_code}. "
                            "Please check your API key and permissions."
                        )

                    # Handle Rate Limit (429)
                    if resp.status_code == 429:
                        retry_after_header = resp.headers.get("Retry-After")
                        delay = float(retry_after_header) if retry_after_header and retry_after_header.isdigit() else (2.0 ** attempt + random.uniform(0.1, 0.5))
                        if attempt == max_retries:
                            raise LLMRateLimitError(f"HTTP 429 Too Many Requests after {max_retries} retries.")
                        logger.warning("HTTP 429 received, backing off for %.2fs (attempt %d/%d)", delay, attempt + 1, max_retries)
                        await asyncio.sleep(delay)
                        continue

                    # Handle 5xx server errors
                    if resp.status_code >= 500:
                        delay = 1.0 * (2.0 ** attempt) + random.uniform(0.1, 0.5)
                        if attempt == max_retries:
                            raise LLMNetworkError(f"Server error HTTP {resp.status_code} after {max_retries} retries.")
                        logger.warning("Server error %d, retrying in %.2fs (attempt %d/%d)", resp.status_code, delay, attempt + 1, max_retries)
                        await asyncio.sleep(delay)
                        continue

                    # Handle other non-200 responses
                    if resp.status_code != 200:
                        raise LLMResponseError(f"Unexpected HTTP {resp.status_code}: {resp.text[:300]}")

                    data = resp.json()
                    choices = data.get("choices")
                    if not choices or not isinstance(choices, list):
                        raise LLMResponseError("Invalid response: 'choices' field missing or empty.")

                    first_choice = choices[0]
                    content = first_choice.get("message", {}).get("content", "")

                    usage = data.get("usage", {})
                    return LLMResponse(
                        content=content or "",
                        model=data.get("model", self.profile.model),
                        prompt_tokens=usage.get("prompt_tokens"),
                        completion_tokens=usage.get("completion_tokens"),
                        raw=data,
                    )

                except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout, httpx.NetworkError) as net_err:
                    last_exception = net_err
                    if attempt == max_retries:
                        raise LLMNetworkError(f"Network error communicating with LLM after {max_retries} retries: {net_err}") from net_err

                    delay = 1.0 * (2.0 ** attempt) + random.uniform(0.1, 0.5)
                    logger.warning("Network issue (%s), retrying in %.2fs (attempt %d/%d)", type(net_err).__name__, delay, attempt + 1, max_retries)
                    await asyncio.sleep(delay)

        raise LLMNetworkError(f"Failed to complete request: {last_exception}")

    async def test_connection(self) -> tuple[bool, str]:
        """Test API connectivity using a minimal prompt. Never logs or leaks API keys."""
        req = LLMRequest(
            messages=[{"role": "user", "content": "ping"}],
            temperature=0.0,
        )
        try:
            resp = await self.complete(req)
            if resp.content:
                return True, "Connection successful."
            return False, "Empty response received."
        except LLMAuthenticationError as auth_err:
            return False, str(auth_err)
        except (LLMError, httpx.HTTPError) as e:
            return False, f"Connection failed: {type(e).__name__} - {e}"
