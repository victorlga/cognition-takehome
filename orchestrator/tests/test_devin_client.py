"""Tests for the Devin API client (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.devin_client import DevinClient


# The client fixture now uses org_id in the base_url, matching the v3 API:
# base_url/organizations/{org_id}/sessions
_BASE = "https://api.test.devin.ai/v3"
_ORG = "test-org"
_EFFECTIVE_BASE = f"{_BASE}/organizations/{_ORG}"


@pytest.fixture
def client():
    return DevinClient(api_key="test-key", org_id=_ORG, base_url=_BASE)


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_creates_session_with_prompt(self, client):
        mock_response = httpx.Response(
            200,
            json={"session_id": "sess-123", "status": "running"},
            request=httpx.Request("POST", f"{_EFFECTIVE_BASE}/sessions"),
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
            request=httpx.Request("POST", f"{_EFFECTIVE_BASE}/sessions"),
        )

        with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
            result = await client.create_session(
                prompt="Test", tags=["issue-1", "planner"]
            )

        assert result["session_id"] == "sess-456"

    @pytest.mark.asyncio
    async def test_creates_session_with_repos_and_title(self, client):
        mock_response = httpx.Response(
            200,
            json={"session_id": "sess-789"},
            request=httpx.Request("POST", f"{_EFFECTIVE_BASE}/sessions"),
        )

        with patch.object(httpx.AsyncClient, "post", return_value=mock_response) as mock_post:
            result = await client.create_session(
                prompt="Test",
                repos=["victorlga/superset"],
                title="[Planner] #1: Fix bug",
            )

        assert result["session_id"] == "sess-789"
        call_kwargs = mock_post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["repos"] == ["victorlga/superset"]
        assert body["title"] == "[Planner] #1: Fix bug"

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self, client):
        mock_response = httpx.Response(
            401,
            json={"error": "unauthorized"},
            request=httpx.Request("POST", f"{_EFFECTIVE_BASE}/sessions"),
        )

        with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
            with pytest.raises(httpx.HTTPStatusError):
                await client.create_session(prompt="should fail")


class TestGetSession:
    @pytest.mark.asyncio
    async def test_returns_session_data(self, client):
        mock_response = httpx.Response(
            200,
            json={"session_id": "sess-123", "status": "running", "status_detail": "finished"},
            request=httpx.Request("GET", f"{_EFFECTIVE_BASE}/sessions/sess-123"),
        )

        with patch.object(httpx.AsyncClient, "get", return_value=mock_response):
            result = await client.get_session("sess-123")

        assert result["status"] == "running"
        assert result["status_detail"] == "finished"


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_sends_message(self, client):
        mock_response = httpx.Response(
            200,
            json={"status": "running"},
            request=httpx.Request("POST", f"{_EFFECTIVE_BASE}/sessions/s/messages"),
        )

        with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
            result = await client.send_message("sess-123", "Hello")

        assert result["status"] == "running"


class TestGetMessages:
    @pytest.mark.asyncio
    async def test_returns_messages_list(self, client):
        messages = [{"role": "user", "content": "hello"}]
        mock_response = httpx.Response(
            200,
            json=messages,
            request=httpx.Request("GET", f"{_EFFECTIVE_BASE}/sessions/s/messages"),
        )

        with patch.object(httpx.AsyncClient, "get", return_value=mock_response):
            result = await client.get_messages("sess-123")

        assert result == messages

    @pytest.mark.asyncio
    async def test_returns_messages_from_dict(self, client):
        messages = [{"role": "assistant", "content": "hi"}]
        mock_response = httpx.Response(
            200,
            json={"messages": messages},
            request=httpx.Request("GET", f"{_EFFECTIVE_BASE}/sessions/s/messages"),
        )

        with patch.object(httpx.AsyncClient, "get", return_value=mock_response):
            result = await client.get_messages("sess-123")

        assert result == messages


class TestPollUntilComplete:
    @pytest.mark.asyncio
    async def test_returns_on_terminal_status_exit(self, client):
        """Session that reaches 'exit' status returns immediately."""
        responses = [
            {"session_id": "s", "status": "running", "status_detail": "working"},
            {"session_id": "s", "status": "exit", "status_detail": ""},
        ]
        call_count = 0

        async def mock_get_session(session_id):
            nonlocal call_count
            r = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            return r

        client.get_session = mock_get_session  # type: ignore[assignment]

        result = await client.poll_until_complete("s", timeout=10, poll_interval=0)
        assert result == "exit"

    @pytest.mark.asyncio
    async def test_returns_on_terminal_status_error(self, client):
        """Session that reaches 'error' status returns immediately."""
        async def mock_get_session(session_id):
            return {"session_id": "s", "status": "error", "status_detail": "error"}

        client.get_session = mock_get_session  # type: ignore[assignment]

        result = await client.poll_until_complete("s", timeout=10, poll_interval=0)
        assert result == "error"

    @pytest.mark.asyncio
    async def test_returns_on_settled_detail_finished(self, client):
        """Session running with status_detail='finished' returns 'running:finished'."""
        async def mock_get_session(session_id):
            return {"session_id": "s", "status": "running", "status_detail": "finished"}

        client.get_session = mock_get_session  # type: ignore[assignment]

        result = await client.poll_until_complete("s", timeout=10, poll_interval=0)
        assert result == "running:finished"

    @pytest.mark.asyncio
    async def test_waiting_for_user_is_not_settled(self, client):
        """'waiting_for_user' should NOT be treated as settled for automated sessions."""
        call_count = 0

        async def mock_get_session(session_id):
            nonlocal call_count
            call_count += 1
            # Always return waiting_for_user — should eventually timeout
            return {"session_id": "s", "status": "running", "status_detail": "waiting_for_user"}

        client.get_session = mock_get_session  # type: ignore[assignment]

        result = await client.poll_until_complete("s", timeout=0, poll_interval=0)
        assert result == "timeout"

    @pytest.mark.asyncio
    async def test_returns_timeout(self, client):
        async def mock_get_session(session_id):
            return {"session_id": "s", "status": "running", "status_detail": "working"}

        client.get_session = mock_get_session  # type: ignore[assignment]

        result = await client.poll_until_complete("s", timeout=0, poll_interval=0)
        assert result == "timeout"
