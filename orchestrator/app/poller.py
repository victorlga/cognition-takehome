"""Polling-based state machine driver.

Replaces inbound webhooks as the **primary** trigger.  Periodically polls
the GitHub API for issues carrying ``state:*`` labels on the tracked
repository and fires state transitions when a label-derived state differs
from the orchestrator's internal DB state.

This eliminates the need for a publicly-reachable webhook endpoint,
so ``docker compose up`` works out of the box with no tunnel or deploy.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app import db
from app.config import settings
from app.devin_client import DevinClient
from app.github_client import GitHubClient
from app.state_machine import handle_status_change

logger = logging.getLogger(__name__)

# The label that marks issues as tracked by the orchestrator.
TRACKING_LABEL = "remediation-target"

# Recognised ``state:`` label suffixes → internal status values.
LABEL_STATUS_MAP: dict[str, str] = {
    "planning": "planning",
    "building": "building",
    "reviewing": "reviewing",
    "done": "done",
}

# Ordered from most-advanced to least-advanced so that when an issue
# carries multiple ``state:*`` labels we pick the most progressed one.
_STATUS_PRIORITY: list[str] = ["done", "reviewing", "building", "planning"]


def extract_state_from_labels(labels: list[dict[str, Any]]) -> str | None:
    """Derive the pipeline state from an issue's label list.

    If multiple ``state:*`` labels are present, the most advanced state
    wins (e.g. ``state:building`` beats ``state:planning``).

    Returns the internal status string, or ``None`` if no ``state:*``
    label is found.
    """
    found: set[str] = set()
    for label in labels:
        name: str = label.get("name", "")
        if not name.lower().startswith("state:"):
            continue
        suffix = name[len("state:"):].lower().strip()
        status = LABEL_STATUS_MAP.get(suffix)
        if status:
            found.add(status)

    if not found:
        return None

    # Return the most-advanced status.
    for s in _STATUS_PRIORITY:
        if s in found:
            return s
    return None


async def poll_once(
    github: GitHubClient | None = None,
    devin: DevinClient | None = None,
) -> list[dict[str, Any]]:
    """Execute a single poll cycle.

    1. Fetch all open issues on the repo carrying the tracking label.
    2. For each issue, extract the ``state:*`` label.
    3. Compare against the DB state.
    4. If the label-based state differs **and** the transition is valid,
       delegate to :func:`handle_status_change`.

    Returns a list of action-result dicts (one per triggered transition).
    """
    github = github or GitHubClient()
    actions: list[dict[str, Any]] = []

    try:
        issues = await github.list_issues_with_labels([TRACKING_LABEL])
    except Exception:
        logger.exception("Poller: failed to fetch issues from GitHub")
        return actions

    for issue in issues:
        issue_number: int | None = issue.get("number")
        if not issue_number:
            continue

        label_state = extract_state_from_labels(issue.get("labels", []))
        if label_state is None:
            # No state:* label on this issue — nothing to do.
            continue

        # Check current DB state to avoid duplicate transitions.
        existing = await db.get_issue(issue_number)
        db_status = existing["status"] if existing else "backlog"

        if db_status == label_state:
            # Already in sync — skip.
            continue

        logger.info(
            "Poller: issue #%d label state '%s' differs from DB state '%s' — triggering transition",
            issue_number,
            label_state,
            db_status,
        )

        result = await handle_status_change(
            issue_number=issue_number,
            new_status=label_state,
            issue_title=issue.get("title", ""),
            issue_body=issue.get("body", "") or "",
            issue_url=issue.get("html_url", ""),
            issue_node_id=issue.get("node_id", ""),
            devin=devin,
            github=github,
        )
        actions.append(result)

    return actions


async def start_polling_loop() -> None:
    """Run :func:`poll_once` in an infinite loop.

    Reads the interval from ``settings.poll_interval_seconds``.
    Exceptions inside a cycle are caught and logged so the loop never
    crashes.
    """
    interval = settings.poll_interval_seconds
    logger.info("Poller started — polling every %d seconds", interval)

    while True:
        try:
            actions = await poll_once()
            if actions:
                logger.info("Poller cycle: %d transition(s) triggered", len(actions))
        except asyncio.CancelledError:
            logger.info("Poller cancelled — shutting down")
            raise
        except Exception:
            logger.exception("Poller cycle failed — will retry next cycle")

        await asyncio.sleep(interval)
