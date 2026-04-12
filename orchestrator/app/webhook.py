"""GitHub webhook endpoint for issue label events.

Since ``projects_v2_item`` webhooks are not supported on repository-level
webhooks for user-owned repos, the orchestrator uses **issue label
transitions** as the primary state-machine driver.  A ``state:<status>``
label added to an issue triggers the corresponding pipeline transition.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, Request, Response

from app.config import settings
from app.github_client import verify_signature
from app.state_machine import handle_status_change

logger = logging.getLogger(__name__)
router = APIRouter()

# Label prefix used to encode pipeline status on GitHub issues.
STATE_LABEL_PREFIX = "state:"

# Maps state label suffixes to internal status values.
LABEL_STATUS_MAP: dict[str, str] = {
    "planning": "planning",
    "building": "building",
    "reviewing": "reviewing",
    "done": "done",
}


def _extract_status_from_label(label_name: str) -> str | None:
    """Return the internal status if *label_name* is a state label, else ``None``."""
    if not label_name.lower().startswith(STATE_LABEL_PREFIX):
        return None
    suffix = label_name[len(STATE_LABEL_PREFIX):].lower().strip()
    return LABEL_STATUS_MAP.get(suffix)


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default="", alias="X-GitHub-Event"),
    x_hub_signature_256: str = Header(default="", alias="X-Hub-Signature-256"),
) -> Response:
    """Receive and process GitHub webhook deliveries.

    Verifies the HMAC-SHA256 signature, then dispatches based on event type.
    """
    body = await request.body()

    # 1. Verify signature
    if settings.github_webhook_secret:
        if not verify_signature(body, x_hub_signature_256, settings.github_webhook_secret):
            logger.warning("Invalid webhook signature")
            return Response(content="Invalid signature", status_code=401)

    payload = await request.json()

    # 2. Route by event type
    if x_github_event == "issues":
        return await _handle_issues_event(payload)

    if x_github_event == "ping":
        return Response(content='{"status": "pong"}', status_code=200, media_type="application/json")

    # Unhandled event type -- acknowledge but do nothing
    logger.debug("Ignoring event type: %s", x_github_event)
    return Response(
        content='{"status": "ignored"}',
        status_code=200,
        media_type="application/json",
    )


async def _handle_issues_event(payload: dict) -> Response:
    """Handle an ``issues`` webhook event.

    We only care about the ``labeled`` action where a ``state:*`` label is
    applied, which signals a pipeline status transition.
    """
    action = payload.get("action")
    if action != "labeled":
        return Response(
            content=json.dumps({"status": "ignored", "reason": "action_not_labeled"}),
            status_code=200,
            media_type="application/json",
        )

    label = payload.get("label", {})
    label_name: str = label.get("name", "")
    new_status = _extract_status_from_label(label_name)

    if new_status is None:
        logger.debug("Ignoring non-state label: %s", label_name)
        return Response(
            content=json.dumps({"status": "ignored", "reason": "not_a_state_label"}),
            status_code=200,
            media_type="application/json",
        )

    issue = payload.get("issue", {})
    issue_number: int | None = issue.get("number")
    if not issue_number:
        return Response(
            content=json.dumps({"status": "ignored", "reason": "missing_issue_number"}),
            status_code=200,
            media_type="application/json",
        )

    issue_title: str = issue.get("title", "")
    issue_body: str = issue.get("body", "") or ""
    issue_url: str = issue.get("html_url", "")
    issue_node_id: str = issue.get("node_id", "")

    logger.info(
        "Issue #%d labeled '%s' -> status '%s'",
        issue_number, label_name, new_status,
    )

    result = await handle_status_change(
        issue_number=issue_number,
        new_status=new_status,
        issue_title=issue_title,
        issue_body=issue_body,
        issue_url=issue_url,
        issue_node_id=issue_node_id,
    )

    return Response(
        content=json.dumps({"status": "processed", **result}),
        status_code=200,
        media_type="application/json",
    )
