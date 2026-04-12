"""Async helpers for the GitHub REST & GraphQL APIs."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GITHUB_GRAPHQL = "https://api.github.com/graphql"


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

    # -- GraphQL helpers -----------------------------------------------------

    async def resolve_issue_from_node_id(self, node_id: str) -> dict[str, Any] | None:
        """Resolve a project item's content_node_id to issue details via GraphQL."""
        query = """
        query($nodeId: ID!) {
          node(id: $nodeId) {
            ... on Issue {
              number
              title
              body
              url
              labels(first: 10) { nodes { name } }
            }
          }
        }
        """
        client = await self._get_client()
        try:
            resp = await client.post(
                GITHUB_GRAPHQL,
                json={"query": query, "variables": {"nodeId": node_id}},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            logger.exception("GraphQL request failed for node %s", node_id)
            return None
        data = resp.json()
        node = data.get("data", {}).get("node")
        if node and node.get("number"):
            return node
        return None

    async def get_project_item_status(self, item_node_id: str) -> str | None:
        """Read the Status single-select field value from a project item via GraphQL."""
        query = """
        query($nodeId: ID!) {
          node(id: $nodeId) {
            ... on ProjectV2Item {
              fieldValueByName(name: "Status") {
                ... on ProjectV2ItemFieldSingleSelectValue {
                  name
                }
              }
            }
          }
        }
        """
        client = await self._get_client()
        resp = await client.post(
            GITHUB_GRAPHQL,
            json={"query": query, "variables": {"nodeId": item_node_id}},
        )
        resp.raise_for_status()
        data = resp.json()
        field_value = (
            data.get("data", {})
            .get("node", {})
            .get("fieldValueByName")
        )
        if field_value:
            return field_value.get("name")
        return None


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------

def verify_signature(payload_body: bytes, signature_header: str, secret: str) -> bool:
    """Verify the HMAC-SHA256 signature from GitHub webhooks.

    Args:
        payload_body: Raw request body bytes.
        signature_header: Value of the X-Hub-Signature-256 header
                          (e.g. "sha256=abc123...").
        secret: The webhook secret string.

    Returns:
        True if the signature is valid, False otherwise.
    """
    if not signature_header:
        return False

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)
