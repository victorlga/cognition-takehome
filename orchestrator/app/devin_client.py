"""Async wrapper around the Devin API v3."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Devin API v3 status enum: new | creating | claimed | running | exit | error | suspended | resuming
# Terminal statuses indicate the session is no longer active.
TERMINAL_STATUSES = frozenset({"exit", "error", "suspended"})

# status_detail values that indicate successful task completion.
# For an automated orchestrator, only "finished" counts as settled —
# "waiting_for_user" and "waiting_for_approval" mean the session is stuck.
SETTLED_DETAIL = frozenset({"finished"})


class DevinClient:
    """Thin async client for the Devin REST API v3."""

    def __init__(
        self,
        api_key: str | None = None,
        org_id: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.devin_api_key
        self.org_id = org_id or settings.devin_org_id
        self.base_url = (base_url or settings.devin_api_base).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    # -- lifecycle -----------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            # v3 endpoints require org_id in the URL path:
            # /v3/organizations/{org_id}/sessions, etc.
            self._client = httpx.AsyncClient(
                base_url=f"{self.base_url}/organizations/{self.org_id}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # -- sessions ------------------------------------------------------------

    async def create_session(
        self,
        prompt: str,
        playbook_id: str | None = None,
        tags: list[str] | None = None,
        repos: list[str] | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Devin session.

        POST /v3/organizations/{org_id}/sessions
        """
        client = await self._get_client()
        body: dict[str, Any] = {"prompt": prompt}
        if playbook_id:
            body["playbook_id"] = playbook_id
        if tags:
            body["tags"] = tags
        if repos:
            body["repos"] = repos
        if title:
            body["title"] = title

        resp = await client.post("/sessions", json=body)
        resp.raise_for_status()
        return resp.json()

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """GET /v3/organizations/{org_id}/sessions/{session_id}"""
        client = await self._get_client()
        resp = await client.get(f"/sessions/{session_id}")
        resp.raise_for_status()
        return resp.json()

    async def send_message(self, session_id: str, message: str) -> dict[str, Any]:
        """POST /v3/organizations/{org_id}/sessions/{session_id}/messages"""
        client = await self._get_client()
        resp = await client.post(
            f"/sessions/{session_id}/messages",
            json={"message": message},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """GET /v3/organizations/{org_id}/sessions/{session_id}/messages"""
        client = await self._get_client()
        resp = await client.get(f"/sessions/{session_id}/messages")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("messages", [])

    async def poll_until_complete(
        self,
        session_id: str,
        timeout: int = 7200,
        poll_interval: int = 30,
    ) -> str:
        """Poll a session until it reaches a terminal or settled state.

        Returns the final status string.
        """
        elapsed = 0
        while elapsed < timeout:
            session = await self.get_session(session_id)
            status = session.get("status", "")
            status_detail = session.get("status_detail", "")

            if status in TERMINAL_STATUSES:
                return status
            if status == "running" and status_detail in SETTLED_DETAIL:
                return f"{status}:{status_detail}"

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        logger.warning("Session %s timed out after %ds", session_id, timeout)
        return "timeout"
