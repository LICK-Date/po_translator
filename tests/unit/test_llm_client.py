"""Unit tests for FakeLLMClient and OpenAICompatibleClient."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from po_translator.exceptions import (
    LLMAuthenticationError,
    LLMNetworkError,
)
from po_translator.llm.client import OpenAICompatibleClient
from po_translator.llm.fake_client import FakeLLMClient
from po_translator.llm.models import LLMProfile, LLMRequest, Message


class TestFakeLLMClient:
    @pytest.mark.asyncio
    async def test_fake_client_echo_batch(self):
        client = FakeLLMClient()
        batch_json = json.dumps({"entries": [{"id": "1", "text": "Game"}]})
        req = LLMRequest(messages=[Message(role="user", content=batch_json)])

        resp = await client.complete(req)
        assert "Translated: Game" in resp.content
        data = json.loads(resp.content)
        assert data["translations"][0]["id"] == "1"

    @pytest.mark.asyncio
    async def test_fake_client_canned_queue(self):
        client = FakeLLMClient()
        client.queue_response('{"test": 123}')
        client.queue_response(LLMNetworkError("Simulated timeout"))

        req = LLMRequest(messages=[Message(role="user", content="hello")])

        resp = await client.complete(req)
        assert resp.content == '{"test": 123}'

        with pytest.raises(LLMNetworkError, match="Simulated timeout"):
            await client.complete(req)


class TestOpenAICompatibleClient:
    def get_profile(self, **kwargs) -> LLMProfile:
        defaults = {
            "name": "test",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-secret-key-123",
            "model": "gpt-4o",
            "temperature": 0.0,
            "timeout_seconds": 5.0,
            "max_retries": 2,
        }
        defaults.update(kwargs)
        return LLMProfile(**defaults)

    @pytest.mark.asyncio
    async def test_successful_completion(self):
        profile = self.get_profile()
        client = OpenAICompatibleClient(profile)

        fake_resp_data = {
            "model": "gpt-4o",
            "choices": [{"message": {"role": "assistant", "content": '{"translations": []}'}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8},
        }

        mock_response = httpx.Response(
            status_code=200,
            json=fake_resp_data,
            request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            req = LLMRequest(
                system_prompt="Translate",
                messages=[Message(role="user", content="Hello")],
                response_schema={"type": "object"},
            )

            resp = await client.complete(req)

            assert resp.content == '{"translations": []}'
            assert resp.prompt_tokens == 12
            assert resp.completion_tokens == 8

            # Verify request headers and URL
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            call_headers = mock_post.call_args[1]["headers"]
            assert call_url == "https://api.example.com/v1/chat/completions"
            assert call_headers["Authorization"] == "Bearer sk-secret-key-123"

    @pytest.mark.asyncio
    async def test_auth_failure_stops_without_retry(self):
        profile = self.get_profile(max_retries=3)
        client = OpenAICompatibleClient(profile)

        mock_response = httpx.Response(
            status_code=401,
            json={"error": "Invalid API Key"},
            request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            req = LLMRequest(messages=[Message(role="user", content="Test")])

            with pytest.raises(LLMAuthenticationError, match="401"):
                await client.complete(req)

            # Must NOT retry on 401
            assert mock_post.call_count == 1

    @pytest.mark.asyncio
    async def test_429_retry_and_recovery(self):
        profile = self.get_profile(max_retries=2)
        client = OpenAICompatibleClient(profile)

        resp_429 = httpx.Response(
            status_code=429,
            headers={"Retry-After": "0.01"},
            request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
        )
        resp_200 = httpx.Response(
            status_code=200,
            json={"choices": [{"message": {"content": "recovered"}}]},
            request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_post.side_effect = [resp_429, resp_200]

            req = LLMRequest(messages=[Message(role="user", content="Test")])
            resp = await client.complete(req)

            assert resp.content == "recovered"
            assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_500_server_error_exhausts_retries(self):
        profile = self.get_profile(max_retries=1)
        client = OpenAICompatibleClient(profile)

        resp_500 = httpx.Response(
            status_code=500,
            request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_post.side_effect = [resp_500, resp_500]

            req = LLMRequest(messages=[Message(role="user", content="Test")])
            with pytest.raises(LLMNetworkError, match="Server error HTTP 500"):
                await client.complete(req)

            assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_test_connection_methods(self):
        profile = self.get_profile()
        client = OpenAICompatibleClient(profile)

        # Successful case
        resp_200 = httpx.Response(
            status_code=200,
            json={"choices": [{"message": {"content": "pong"}}]},
            request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = resp_200
            ok, msg = await client.test_connection()
            assert ok is True
            assert "successful" in msg

        # 401 Unauthorized case
        resp_401 = httpx.Response(
            status_code=401,
            request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = resp_401
            ok, msg = await client.test_connection()
            assert ok is False
            assert "authentication failed" in msg
