"""Async helpers for the GitHub REST & GraphQL APIs."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubClient:
    """Thin async wrapper around the GitHub APIs needed by the orchestrator."""

    def __init__(self, token: str | None = None, repo: str | None = None) -> None:
        self.token = token or settings.github_token
        self.repo = repo or settings.github_repo
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # -- REST helpers --------------------------------------------------------

    async def list_issues_with_labels(
        self, labels: list[str], state: str = "open",
    ) -> list[dict[str, Any]]:
        """Fetch issues that carry **all** of the given labels.

        Uses ``GET /repos/{repo}/issues?labels=...&state=...``.
        Returns the full issue JSON objects (number, title, body, labels, etc.).
        Handles pagination automatically (up to 10 pages / 1 000 issues).
        """
        client = await self._get_client()
        label_param = ",".join(labels)
        all_issues: list[dict[str, Any]] = []
        page = 1
        while page <= 10:
            resp = await client.get(
                f"{GITHUB_API}/repos/{self.repo}/issues",
                params={
                    "labels": label_param,
                    "state": state,
                    "per_page": 100,
                    "page": page,
                },
            )
            resp.raise_for_status()
            batch: list[dict[str, Any]] = resp.json()
            if not batch:
                break
            all_issues.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return all_issues
