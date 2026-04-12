"""Issue state machine — maps status transitions to Devin session creation."""

from __future__ import annotations

import logging
from typing import Any

from app import db
from app.devin_client import DevinClient
from app.github_client import GitHubClient
from app.prompts import IssueContext, build_builder_prompt, build_planner_prompt, build_reviewer_prompt

logger = logging.getLogger(__name__)

# Valid status transitions (old_status -> set of allowed new_statuses)
VALID_TRANSITIONS: dict[str, set[str]] = {
    "backlog": {"planning"},
    "planning": {"building"},
    "building": {"reviewing"},
    "reviewing": {"done"},
}

# Any status can transition to "error"
for _status in list(VALID_TRANSITIONS):
    VALID_TRANSITIONS[_status].add("error")


def is_valid_transition(old_status: str, new_status: str) -> bool:
    """Check whether a status transition is allowed."""
    allowed = VALID_TRANSITIONS.get(old_status, set())
    return new_status in allowed


async def handle_status_change(
    content_node_id: str,
    new_status: str,
    project_item_id: int | None = None,
    devin: DevinClient | None = None,
    github: GitHubClient | None = None,
) -> dict[str, Any]:
    """Main entry point: react to a status field change on the project board.

    Returns a dict summarising the action taken.
    """
    devin = devin or DevinClient()
    github = github or GitHubClient()

    # Resolve the issue from the content node ID
    issue_data = await github.resolve_issue_from_node_id(content_node_id)
    if issue_data is None:
        logger.warning("Could not resolve node %s to an issue", content_node_id)
        return {"action": "skipped", "reason": "unresolvable_node_id"}

    issue_number: int = issue_data["number"]
    issue_title: str = issue_data.get("title", "")
    issue_body: str = issue_data.get("body", "")
    issue_url: str = issue_data.get("url", "")

    # Ensure we have a local record
    existing = await db.get_issue(issue_number)
    old_status = existing["status"] if existing else "backlog"

    # Normalise status names (GitHub Project fields are user-defined)
    new_status_lower = new_status.lower().strip()

    if not is_valid_transition(old_status, new_status_lower):
        logger.info(
            "Invalid transition for issue #%d: %s -> %s",
            issue_number, old_status, new_status_lower,
        )
        return {
            "action": "rejected",
            "reason": "invalid_transition",
            "old_status": old_status,
            "new_status": new_status_lower,
        }

    # Build context object used by prompt builders
    ctx = IssueContext(
        issue_url=issue_url,
        issue_title=issue_title,
        issue_body=issue_body,
        issue_number=issue_number,
    )

    result: dict[str, Any] = {
        "action": "transitioned",
        "issue_number": issue_number,
        "old_status": old_status,
        "new_status": new_status_lower,
    }

    # Upsert base fields
    update_fields: dict[str, Any] = {
        "issue_node_id": content_node_id,
        "title": issue_title,
        "status": new_status_lower,
    }
    if project_item_id is not None:
        update_fields["project_item_id"] = project_item_id

    # Handle each transition
    if new_status_lower == "planning":
        update_fields["planning_started_at"] = db._now()
        prompt = build_planner_prompt(ctx)
        try:
            session = await devin.create_session(
                prompt=prompt,
                tags=[f"issue-{issue_number}", "planner"],
            )
            session_id = session.get("session_id", "")
            update_fields["planner_session"] = session_id
            await db.insert_session_log(issue_number, session_id, "planner")
            result["session_id"] = session_id
            logger.info("Spawned planner session %s for issue #%d", session_id, issue_number)
        except Exception:
            logger.exception("Failed to create planner session for issue #%d", issue_number)
            update_fields["status"] = "error"
            update_fields["error_message"] = "Failed to create planner session"
            result["action"] = "error"

    elif new_status_lower == "building":
        update_fields["building_started_at"] = db._now()
        # Retrieve plan text from existing record or issue comments
        plan_text = (existing or {}).get("plan_text", "")
        if not plan_text:
            plan_text = "(Plan not cached — check the issue comments for the approved plan.)"
        prompt = build_builder_prompt(ctx, plan_text)
        try:
            session = await devin.create_session(
                prompt=prompt,
                tags=[f"issue-{issue_number}", "builder"],
            )
            session_id = session.get("session_id", "")
            update_fields["builder_session"] = session_id
            await db.insert_session_log(issue_number, session_id, "builder")
            result["session_id"] = session_id
            logger.info("Spawned builder session %s for issue #%d", session_id, issue_number)
        except Exception:
            logger.exception("Failed to create builder session for issue #%d", issue_number)
            update_fields["status"] = "error"
            update_fields["error_message"] = "Failed to create builder session"
            result["action"] = "error"

    elif new_status_lower == "reviewing":
        update_fields["reviewing_started_at"] = db._now()
        pr_url = (existing or {}).get("pr_url", "")
        if not pr_url:
            pr_url = "(PR URL not cached — check the issue comments.)"
        prompt = build_reviewer_prompt(ctx, pr_url)
        try:
            session = await devin.create_session(
                prompt=prompt,
                tags=[f"issue-{issue_number}", "reviewer"],
            )
            session_id = session.get("session_id", "")
            update_fields["reviewer_session"] = session_id
            await db.insert_session_log(issue_number, session_id, "reviewer")
            result["session_id"] = session_id
            logger.info("Spawned reviewer session %s for issue #%d", session_id, issue_number)
        except Exception:
            logger.exception("Failed to create reviewer session for issue #%d", issue_number)
            update_fields["status"] = "error"
            update_fields["error_message"] = "Failed to create reviewer session"
            result["action"] = "error"

    elif new_status_lower == "done":
        update_fields["done_at"] = db._now()
        logger.info("Issue #%d marked as done", issue_number)

    elif new_status_lower == "error":
        update_fields["error_message"] = "Manually moved to error"
        logger.warning("Issue #%d moved to error state", issue_number)

    await db.upsert_issue(issue_number, **update_fields)
    return result
