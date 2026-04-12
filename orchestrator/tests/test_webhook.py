"""Tests for the webhook endpoint — HMAC verification, payload parsing, event routing."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.github_client import verify_signature
from app.main import app


def _sign(payload: bytes, secret: str) -> str:
    """Compute the X-Hub-Signature-256 header value."""
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@pytest.fixture
def webhook_secret():
    """Ensure a known webhook secret for tests."""
    original = settings.github_webhook_secret
    settings.github_webhook_secret = "test-secret-123"
    yield "test-secret-123"
    settings.github_webhook_secret = original


@pytest.fixture
def sample_payload():
    return {
        "action": "edited",
        "changes": {
            "field_value": {
                "field_node_id": "PVTSSF_test",
                "field_type": "single_select",
                "to": {"name": "Planning"},
            }
        },
        "projects_v2_item": {
            "id": 12345,
            "node_id": "PVTI_test",
            "content_node_id": "I_test_node",
            "content_type": "Issue",
        },
    }


# ---------------------------------------------------------------------------
# Signature verification unit tests
# ---------------------------------------------------------------------------


class TestVerifySignature:
    def test_valid_signature(self):
        body = b'{"hello": "world"}'
        secret = "my-secret"
        sig = _sign(body, secret)
        assert verify_signature(body, sig, secret) is True

    def test_invalid_signature(self):
        body = b'{"hello": "world"}'
        assert verify_signature(body, "sha256=bad", "my-secret") is False

    def test_empty_signature_header(self):
        assert verify_signature(b"x", "", "secret") is False

    def test_tampered_body(self):
        body = b'{"a":1}'
        sig = _sign(body, "secret")
        assert verify_signature(b'{"a":2}', sig, "secret") is False


# ---------------------------------------------------------------------------
# Webhook endpoint integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestWebhookEndpoint:
    async def test_ping_event(self, webhook_secret):
        body = b'{"zen": "test"}'
        sig = _sign(body, webhook_secret)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "X-GitHub-Event": "ping",
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "pong"

    async def test_rejects_invalid_signature(self, webhook_secret):
        body = b'{"action": "edited"}'
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "X-GitHub-Event": "projects_v2_item",
                    "X-Hub-Signature-256": "sha256=invalid",
                    "Content-Type": "application/json",
                },
            )
        assert resp.status_code == 401

    async def test_ignores_non_edited_action(self, webhook_secret, sample_payload):
        sample_payload["action"] = "created"
        body = json.dumps(sample_payload).encode()
        sig = _sign(body, webhook_secret)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "X-GitHub-Event": "projects_v2_item",
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["reason"] == "action_not_edited"

    async def test_ignores_non_issue_content(self, webhook_secret, sample_payload):
        sample_payload["projects_v2_item"]["content_type"] = "PullRequest"
        body = json.dumps(sample_payload).encode()
        sig = _sign(body, webhook_secret)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "X-GitHub-Event": "projects_v2_item",
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["reason"] == "not_an_issue"

    async def test_ignores_unhandled_event_type(self, webhook_secret):
        body = b'{"action": "opened"}'
        sig = _sign(body, webhook_secret)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "X-GitHub-Event": "issues",
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHealthCheck:
    async def test_health(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
