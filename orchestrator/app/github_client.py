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

    async def get_issue(self, issue_number: int) -> dict[str, Any]:
        """GET /repos/{owner}/{repo}/issues/{issue_number}"""
        client = await self._get_client()
        resp = await client.get(f"{GITHUB_API}/repos/{self.repo}/issues/{issue_number}")
        resp.raise_for_status()
        return resp.json()

    async def post_issue_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        """POST /repos/{owner}/{repo}/issues/{issue_number}/comments"""
        client = await self._get_client()
        resp = await client.post(
            f"{GITHUB_API}/repos/{self.repo}/issues/{issue_number}/comments",
            json={"body": body},
        )
        resp.raise_for_status()
        return resp.json()

    async def add_labels(self, issue_number: int, labels: list[str]) -> None:
        """Add labels to an issue, creating them first if needed."""
        client = await self._get_client()
        for label in labels:
            # Ensure the label exists on the repo
            resp = await client.get(
                f"{GITHUB_API}/repos/{self.repo}/labels/{label}"
            )
            if resp.status_code == 404:
                await client.post(
                    f"{GITHUB_API}/repos/{self.repo}/labels",
                    json={"name": label, "color": "ededed"},
                )
        # Now add to issue
        await client.post(
            f"{GITHUB_API}/repos/{self.repo}/issues/{issue_number}/labels",
            json={"labels": labels},
        )

    async def remove_label(self, issue_number: int, label: str) -> None:
        """Remove a single label from an issue (ignores 404 if absent)."""
        client = await self._get_client()
        resp = await client.delete(
            f"{GITHUB_API}/repos/{self.repo}/issues/{issue_number}/labels/{label}"
        )
        if resp.status_code not in (200, 404):
            resp.raise_for_status()

    async def set_state_label(self, issue_number: int, new_state: str) -> None:
        """Ensure only one ``state:*`` label is present on the issue.

        Removes any existing ``state:*`` labels, then adds
        ``state:{new_state}``.  This keeps the issue labels consistent with
        the orchestrator's internal state.
        """
        state_prefix = "state:"
        target_label = f"{state_prefix}{new_state}"

        client = await self._get_client()
        resp = await client.get(
            f"{GITHUB_API}/repos/{self.repo}/issues/{issue_number}/labels"
        )
        resp.raise_for_status()
        current_labels: list[dict] = resp.json()

        # Remove stale state labels
        for lbl in current_labels:
            name: str = lbl.get("name", "")
            if name.lower().startswith(state_prefix) and name.lower() != target_label.lower():
                await self.remove_label(issue_number, name)

        # Add the target label (idempotent — GitHub ignores duplicates)
        await self.add_labels(issue_number, [target_label])

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
