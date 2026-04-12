"""Background loop that tracks active Devin sessions to completion.

Complements the poller (which detects *label* changes on GitHub issues)
by polling the *Devin API* for sessions that were created but not yet
finished.  When a session reaches a terminal or settled state the tracker:

1. Updates ``session_log`` with the final status, ``finished_at``, and
   ``duration_seconds``.
2. For **builder** sessions that produced pull requests, stores the first
   PR URL on ``issue_state.pr_url``.
3. For sessions that ended in error, propagates the error to
   ``issue_state.error_message``.
4. Posts a summary comment on the corresponding GitHub issue so that
   the issue thread serves as an audit trail.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app import db
from app.config import settings
from app.devin_client import DevinClient, TERMINAL_STATUSES, SETTLED_DETAIL
from app.github_client import GitHubClient

logger = logging.getLogger(__name__)

# Maps session_type to the issue_state.status where that session is
# the active worker.  Used to detect sessions that have been superseded
# by a pipeline advance (e.g. planner session still "running" after the
# issue moved to "building").
_SESSION_STAGE: dict[str, str] = {
    "planner": "planning",
    "builder": "building",
    "reviewer": "reviewing",
}


def _extract_pr_url(session_data: dict[str, Any]) -> str | None:
    """Return the first PR URL from a Devin session response, or None."""
    for pr in session_data.get("pull_requests", []):
        url = pr.get("pr_url", "")
        if url:
            return url
    return None


def _compute_duration(started_at: str) -> int:
    """Return elapsed seconds between *started_at* (ISO-8601) and now."""
    try:
        start = datetime.fromisoformat(started_at)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - start
        return max(0, int(delta.total_seconds()))
    except (ValueError, TypeError):
        return 0


def _final_status_label(status: str, status_detail: str) -> str:
    """Map a Devin API status/status_detail pair to a session_log status.

    ``session_log.status`` uses the vocabulary: running | completed | failed.
    """
    if status == "running" and status_detail in SETTLED_DETAIL:
        return "completed"
    if status in TERMINAL_STATUSES:
        # "exit" is a clean stop; "error" and "suspended" are failures.
        return "completed" if status == "exit" else "failed"
    return "running"


def _build_status_comment(update: dict[str, Any]) -> str:
    """Build a Markdown comment summarising a session's final state."""
    session_type = update["session_type"]
    final_status = update["final_status"]
    duration = update.get("duration_seconds", 0)
    session_id = update["session_id"]

    minutes = duration // 60
    emoji = "\u2705" if final_status == "completed" else "\u274c"
    header = f"{emoji} **{session_type.capitalize()}** session `{session_id}` — **{final_status}** ({minutes}m)"

    lines = [header]

    pr_url = update.get("pr_url")
    if pr_url:
        lines.append(f"\nPull request: {pr_url}")

    if final_status == "failed":
        api_status = update.get("api_status", "unknown")
        lines.append(f"\nDevin API status: `{api_status}`")

    return "\n".join(lines)


async def check_active_sessions(
    devin: DevinClient | None = None,
    github: GitHubClient | None = None,
) -> list[dict[str, Any]]:
    """Poll every 'running' session in session_log against the Devin API.

    For each session that has reached a terminal or settled state:

    * Update ``session_log`` with final status, finished_at, duration.
    * If it was a **builder** session, extract the PR URL and store it on
      the parent ``issue_state`` row.
    * If the session errored, write the error to ``issue_state``.
    * Post an audit-trail comment on the GitHub issue.

    Returns a list of dicts summarising each update made (useful for
    logging and testing).
    """
    devin = devin or DevinClient()
    github = github or GitHubClient()
    active = await db.list_active_sessions()

    if not active:
        return []

    updates: list[dict[str, Any]] = []

    for row in active:
        session_id: str = row["session_id"]
        issue_id: int = row["issue_id"]
        session_type: str = row["session_type"]
        started_at: str = row["started_at"]

        try:
            session_data = await devin.get_session(session_id)
        except Exception:
            logger.exception(
                "Tracker: failed to poll session %s (issue #%d)",
                session_id,
                issue_id,
            )
            continue

        api_status: str = session_data.get("status", "")
        api_detail: str = session_data.get("status_detail", "") or ""

        log_status = _final_status_label(api_status, api_detail)
        if log_status == "running":
            # Check if the issue has advanced past this session's stage.
            expected_stage = _SESSION_STAGE.get(session_type)
            issue_status: str = row.get("issue_status", "")
            if expected_stage and issue_status != expected_stage:
                # Issue moved on — this session's work is done.
                log_status = "completed"
                logger.info(
                    "Tracker: session %s (%s) superseded — issue #%d moved to '%s'",
                    session_id, session_type, issue_id, issue_status,
                )
            else:
                # Still in progress — nothing to do yet.
                continue

        duration = _compute_duration(started_at)
        await db.update_session_log(session_id, log_status, duration_seconds=duration)

        update: dict[str, Any] = {
            "session_id": session_id,
            "issue_id": issue_id,
            "session_type": session_type,
            "final_status": log_status,
            "api_status": api_status,
            "api_detail": api_detail,
            "duration_seconds": duration,
        }

        # Extract PR URL from builder sessions.
        if session_type == "builder" and log_status == "completed":
            pr_url = _extract_pr_url(session_data)
            if pr_url:
                await db.upsert_issue(issue_id, pr_url=pr_url)
                update["pr_url"] = pr_url
                logger.info(
                    "Tracker: builder session %s produced PR %s for issue #%d",
                    session_id,
                    pr_url,
                    issue_id,
                )

        # Propagate errors to the issue record.
        if log_status == "failed":
            error_msg = f"Devin session {session_id} ({session_type}) ended with status '{api_status}'"
            await db.upsert_issue(issue_id, error_message=error_msg)
            logger.warning(
                "Tracker: session %s failed (%s) for issue #%d",
                session_id,
                api_status,
                issue_id,
            )

        # Post an audit-trail comment on the GitHub issue.
        comment = _build_status_comment(update)
        try:
            await github.post_issue_comment(issue_id, comment)
        except Exception:
            logger.exception(
                "Tracker: failed to post comment on issue #%d", issue_id
            )

        updates.append(update)

        logger.info(
            "Tracker: session %s (%s) for issue #%d → %s (took %ds)",
            session_id,
            session_type,
            issue_id,
            log_status,
            duration,
        )

    return updates


async def start_session_tracker_loop() -> None:
    """Periodically call :func:`check_active_sessions`.

    Uses the same interval as the GitHub poller
    (``settings.poll_interval_seconds``).
    """
    interval = settings.poll_interval_seconds
    logger.info("Session tracker started — checking every %d seconds", interval)

    devin = DevinClient()
    github = GitHubClient()

    while True:
        try:
            updates = await check_active_sessions(devin=devin, github=github)
            if updates:
                logger.info(
                    "Tracker cycle: %d session(s) updated", len(updates)
                )
        except asyncio.CancelledError:
            logger.info("Session tracker cancelled — shutting down")
            raise
        except Exception:
            logger.exception("Tracker cycle failed — will retry next cycle")

        await asyncio.sleep(interval)
