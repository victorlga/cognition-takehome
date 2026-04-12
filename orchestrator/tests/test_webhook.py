"""Tests for the webhook endpoint — HMAC verification, payload parsing, event routing.

The orchestrator uses ``issues`` webhook events with ``state:*`` labels
as the primary trigger (since ``projects_v2_item`` events are not
available on repo-level webhooks for user-owned repos).
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.github_client import verify_signature
from app.main import app
from app.webhook import _extract_status_from_label


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
def labeled_payload():
    """Simulate an ``issues`` webhook with a ``state:planning`` label added."""
    return {
        "action": "labeled",
        "label": {"id": 1, "name": "state:planning", "color": "ededed"},
        "issue": {
            "number": 1,
            "title": "Session cookies not invalidated on logout",
            "body": "After logout, stolen cookies still grant access.",
            "html_url": "https://github.com/victorlga/superset/issues/1",
            "node_id": "I_test_node_1",
            "labels": [
                {"name": "remediation-target"},
                {"name": "state:planning"},
            ],
        },
    }


# ---------------------------------------------------------------------------
# Label extraction unit tests
# ---------------------------------------------------------------------------


class TestExtractStatusFromLabel:
    def test_planning(self):
        assert _extract_status_from_label("state:planning") == "planning"

    def test_building(self):
        assert _extract_status_from_label("state:building") == "building"

    def test_reviewing(self):
        assert _extract_status_from_label("state:reviewing") == "reviewing"

    def test_done(self):
        assert _extract_status_from_label("state:done") == "done"

    def test_case_insensitive(self):
        assert _extract_status_from_label("State:Planning") == "planning"

    def test_non_state_label_returns_none(self):
        assert _extract_status_from_label("remediation-target") is None

    def test_unknown_state_returns_none(self):
        assert _extract_status_from_label("state:unknown") is None

    def test_empty_string_returns_none(self):
        assert _extract_status_from_label("") is None


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
        body = b'{"action": "labeled"}'
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "X-GitHub-Event": "issues",
                    "X-Hub-Signature-256": "sha256=invalid",
                    "Content-Type": "application/json",
                },
            )
        assert resp.status_code == 401

    async def test_ignores_non_labeled_action(self, webhook_secret, labeled_payload):
        labeled_payload["action"] = "opened"
        body = json.dumps(labeled_payload).encode()
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
        assert resp.json()["reason"] == "action_not_labeled"

    async def test_ignores_non_state_label(self, webhook_secret, labeled_payload):
        labeled_payload["label"]["name"] = "bug"
        body = json.dumps(labeled_payload).encode()
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
        assert resp.json()["reason"] == "not_a_state_label"

    async def test_ignores_unhandled_event_type(self, webhook_secret):
        body = b'{"ref": "refs/heads/main"}'
        sig = _sign(body, webhook_secret)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "X-GitHub-Event": "push",
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    async def test_processes_valid_state_label(self, webhook_secret, labeled_payload):
        """A valid ``state:planning`` label on issue #1 should be processed."""
        body = json.dumps(labeled_payload).encode()
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
        data = resp.json()
        assert data["status"] == "processed"
        # The state machine will try to create a Devin session which will
        # fail (no real API key), so expect an error action — but the
        # webhook itself should still return 200.
        assert data.get("issue_number") == 1


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
