"""GitHub webhook endpoint for projects_v2_item events."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, Request, Response

from app.config import settings
from app.github_client import verify_signature
from app.state_machine import handle_status_change

logger = logging.getLogger(__name__)
router = APIRouter()

# Maps commonly-used project board column names to internal status values.
STATUS_MAP: dict[str, str] = {
    "backlog": "backlog",
    "planning": "planning",
    "building": "building",
    "reviewing": "reviewing",
    "done": "done",
    # Allow some flexibility
    "in progress": "building",
    "review": "reviewing",
    "todo": "backlog",
}


def _normalise_status(raw: str) -> str:
    """Map a human-readable project board column name to an internal status."""
    return STATUS_MAP.get(raw.lower().strip(), raw.lower().strip())


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
    if x_github_event == "projects_v2_item":
        return await _handle_project_item(payload)

    if x_github_event == "ping":
        return Response(content='{"status": "pong"}', status_code=200, media_type="application/json")

    # Unhandled event type — acknowledge but do nothing
    logger.debug("Ignoring event type: %s", x_github_event)
    return Response(
        content='{"status": "ignored"}',
        status_code=200,
        media_type="application/json",
    )


async def _handle_project_item(payload: dict) -> Response:
    """Handle a projects_v2_item webhook event."""
    action = payload.get("action")
    if action != "edited":
        return Response(
            content='{"status": "ignored", "reason": "action_not_edited"}',
            status_code=200,
            media_type="application/json",
        )

    changes = payload.get("changes", {})
    field_value = changes.get("field_value")
    if not field_value:
        return Response(
            content='{"status": "ignored", "reason": "no_field_value_change"}',
            status_code=200,
            media_type="application/json",
        )

    item = payload.get("projects_v2_item", {})
    content_node_id: str = item.get("content_node_id", "")
    content_type: str = item.get("content_type", "")
    project_item_id: int | None = item.get("id")

    if content_type != "Issue":
        return Response(
            content='{"status": "ignored", "reason": "not_an_issue"}',
            status_code=200,
            media_type="application/json",
        )

    if not content_node_id:
        return Response(
            content='{"status": "ignored", "reason": "missing_content_node_id"}',
            status_code=200,
            media_type="application/json",
        )

    # Read the new status from the field value.
    # The payload includes `to` with the option details for single_select fields.
    to_value = field_value.get("to", {})
    new_status_raw = ""
    if isinstance(to_value, dict):
        new_status_raw = to_value.get("name", "")
    elif isinstance(to_value, str):
        new_status_raw = to_value

    if not new_status_raw:
        # Try reading from the `field_value` directly
        new_status_raw = field_value.get("value", "")

    if not new_status_raw:
        logger.info("Could not determine new status from payload")
        return Response(
            content='{"status": "ignored", "reason": "unknown_new_status"}',
            status_code=200,
            media_type="application/json",
        )

    new_status = _normalise_status(new_status_raw)
    logger.info(
        "Project item %s (%s) status changed to: %s (raw: %s)",
        project_item_id, content_node_id, new_status, new_status_raw,
    )

    result = await handle_status_change(
        content_node_id=content_node_id,
        new_status=new_status,
        project_item_id=project_item_id,
    )

    return Response(
        content=json.dumps({"status": "processed", **result}),
        status_code=200,
        media_type="application/json",
    )
