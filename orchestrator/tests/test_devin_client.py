"""Tests for the Devin API client (mocked HTTP)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.devin_client import DevinClient


@pytest.fixture
def client():
    return DevinClient(api_key="test-key", org_id="test-org", base_url="https://api.test.devin.ai/v3")


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_creates_session_with_prompt(self, client):
        mock_response = httpx.Response(
            200,
            json={"session_id": "sess-123", "status": "running"},
            request=httpx.Request("POST", "https://api.test.devin.ai/v3/sessions"),
        )

        with patch.object(httpx.AsyncClient, "post", return_value=mock_response) as mock_post:
            result = await client.create_session(prompt="Fix the bug")

        assert result["session_id"] == "sess-123"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["prompt"] == "Fix the bug"

    @pytest.mark.asyncio
    async def test_creates_session_with_tags(self, client):
        mock_response = httpx.Response(
            200,
            json={"session_id": "sess-456"},
            request=httpx.Request("POST", "https://api.test.devin.ai/v3/sessions"),
        )

        with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
            result = await client.create_session(
                prompt="Test", tags=["issue-1", "planner"]
            )

        assert result["session_id"] == "sess-456"

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self, client):
        mock_response = httpx.Response(
            401,
            json={"error": "unauthorized"},
            request=httpx.Request("POST", "https://api.test.devin.ai/v3/sessions"),
        )

        with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
            with pytest.raises(httpx.HTTPStatusError):
                await client.create_session(prompt="should fail")


class TestGetSession:
    @pytest.mark.asyncio
    async def test_returns_session_data(self, client):
        mock_response = httpx.Response(
            200,
            json={"session_id": "sess-123", "status": "finished"},
            request=httpx.Request("GET", "https://api.test.devin.ai/v3/sessions/sess-123"),
        )

        with patch.object(httpx.AsyncClient, "get", return_value=mock_response):
            result = await client.get_session("sess-123")

        assert result["status"] == "finished"


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_sends_message(self, client):
        mock_response = httpx.Response(
            200,
            json={"status": "ok"},
            request=httpx.Request("POST", "https://api.test.devin.ai/v3/sessions/s/messages"),
        )

        with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
            result = await client.send_message("sess-123", "Hello")

        assert result["status"] == "ok"


class TestPollUntilComplete:
    @pytest.mark.asyncio
    async def test_returns_on_terminal_status(self, client):
        responses = [
            {"session_id": "s", "status": "running", "status_detail": ""},
            {"session_id": "s", "status": "finished", "status_detail": ""},
        ]
        call_count = 0

        async def mock_get_session(session_id):
            nonlocal call_count
            r = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            return r

        client.get_session = mock_get_session  # type: ignore[assignment]

        result = await client.poll_until_complete("s", timeout=10, poll_interval=0)
        assert result == "finished"

    @pytest.mark.asyncio
    async def test_returns_timeout(self, client):
        async def mock_get_session(session_id):
            return {"session_id": "s", "status": "running", "status_detail": ""}

        client.get_session = mock_get_session  # type: ignore[assignment]

        result = await client.poll_until_complete("s", timeout=0, poll_interval=0)
        assert result == "timeout"
