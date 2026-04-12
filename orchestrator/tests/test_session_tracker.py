"""Tests for the session tracker — polls active Devin sessions to completion."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app import db
from app.session_tracker import (
    _build_status_comment,
    _compute_duration,
    _extract_pr_url,
    _final_status_label,
    check_active_sessions,
)


class TestExtractPrUrl:
    def test_extracts_first_pr_url(self):
        data = {
            "pull_requests": [
                {"pr_url": "https://github.com/org/repo/pull/1", "pr_state": "open"},
                {"pr_url": "https://github.com/org/repo/pull/2", "pr_state": "merged"},
            ]
        }
        assert _extract_pr_url(data) == "https://github.com/org/repo/pull/1"

    def test_returns_none_when_empty(self):
        assert _extract_pr_url({"pull_requests": []}) is None

    def test_returns_none_when_missing(self):
        assert _extract_pr_url({}) is None

    def test_skips_empty_pr_url(self):
        data = {
            "pull_requests": [
                {"pr_url": "", "pr_state": ""},
                {"pr_url": "https://github.com/org/repo/pull/3", "pr_state": "open"},
            ]
        }
        assert _extract_pr_url(data) == "https://github.com/org/repo/pull/3"


class TestFinalStatusLabel:
    def test_running_finished_is_completed(self):
        assert _final_status_label("running", "finished") == "completed"

    def test_exit_is_completed(self):
        assert _final_status_label("exit", "") == "completed"

    def test_error_is_failed(self):
        assert _final_status_label("error", "") == "failed"

    def test_suspended_is_failed(self):
        assert _final_status_label("suspended", "inactivity") == "failed"

    def test_running_working_is_running(self):
        assert _final_status_label("running", "working") == "running"

    def test_running_waiting_for_user_is_running(self):
        assert _final_status_label("running", "waiting_for_user") == "running"


class TestComputeDuration:
    def test_returns_non_negative(self):
        # A recent timestamp should give a small positive number.
        from app.db import now_utc

        result = _compute_duration(now_utc())
        assert result >= 0

    def test_handles_invalid_input(self):
        assert _compute_duration("not-a-date") == 0
        assert _compute_duration("") == 0


@pytest.mark.asyncio
class TestCheckActiveSessions:
    async def test_no_active_sessions_returns_empty(self):
        mock_devin = AsyncMock()
        mock_github = AsyncMock()
        result = await check_active_sessions(devin=mock_devin, github=mock_github)
        assert result == []
        mock_devin.get_session.assert_not_called()

    async def test_updates_completed_session(self):
        """A session that finished should be marked completed in session_log."""
        await db.upsert_issue(1, issue_node_id="I_1", status="planning")
        await db.insert_session_log(1, "sess-1", "planner")

        mock_devin = AsyncMock()
        mock_devin.get_session.return_value = {
            "session_id": "sess-1",
            "status": "running",
            "status_detail": "finished",
            "pull_requests": [],
        }
        mock_github = AsyncMock()

        updates = await check_active_sessions(devin=mock_devin, github=mock_github)

        assert len(updates) == 1
        assert updates[0]["session_id"] == "sess-1"
        assert updates[0]["final_status"] == "completed"

        logs = await db.list_session_logs(issue_id=1)
        assert logs[0]["status"] == "completed"
        assert logs[0]["finished_at"] is not None
        assert logs[0]["duration_seconds"] >= 0
        mock_github.post_issue_comment.assert_called_once()

    async def test_extracts_pr_url_from_builder_session(self):
        """A completed builder session with PRs should update issue_state.pr_url."""
        await db.upsert_issue(2, issue_node_id="I_2", status="building")
        await db.insert_session_log(2, "sess-2", "builder")

        mock_devin = AsyncMock()
        mock_devin.get_session.return_value = {
            "session_id": "sess-2",
            "status": "running",
            "status_detail": "finished",
            "pull_requests": [
                {"pr_url": "https://github.com/org/repo/pull/5", "pr_state": "open"}
            ],
        }
        mock_github = AsyncMock()

        updates = await check_active_sessions(devin=mock_devin, github=mock_github)

        assert len(updates) == 1
        assert updates[0]["pr_url"] == "https://github.com/org/repo/pull/5"

        issue = await db.get_issue(2)
        assert issue["pr_url"] == "https://github.com/org/repo/pull/5"

    async def test_does_not_extract_pr_from_planner_session(self):
        """PR extraction only applies to builder sessions."""
        await db.upsert_issue(3, issue_node_id="I_3", status="planning")
        await db.insert_session_log(3, "sess-3", "planner")

        mock_devin = AsyncMock()
        mock_devin.get_session.return_value = {
            "session_id": "sess-3",
            "status": "running",
            "status_detail": "finished",
            "pull_requests": [
                {"pr_url": "https://github.com/org/repo/pull/99", "pr_state": "open"}
            ],
        }
        mock_github = AsyncMock()

        updates = await check_active_sessions(devin=mock_devin, github=mock_github)

        assert len(updates) == 1
        assert "pr_url" not in updates[0]

    async def test_propagates_error_to_issue(self):
        """A session that errored should update issue_state.error_message."""
        await db.upsert_issue(4, issue_node_id="I_4", status="building")
        await db.insert_session_log(4, "sess-4", "builder")

        mock_devin = AsyncMock()
        mock_devin.get_session.return_value = {
            "session_id": "sess-4",
            "status": "error",
            "status_detail": "error",
            "pull_requests": [],
        }
        mock_github = AsyncMock()

        updates = await check_active_sessions(devin=mock_devin, github=mock_github)

        assert len(updates) == 1
        assert updates[0]["final_status"] == "failed"

        issue = await db.get_issue(4)
        assert "sess-4" in issue["error_message"]
        assert "builder" in issue["error_message"]

    async def test_skips_still_running_sessions(self):
        """Sessions still actively working should not be updated."""
        await db.upsert_issue(5, issue_node_id="I_5", status="planning")
        await db.insert_session_log(5, "sess-5", "planner")

        mock_devin = AsyncMock()
        mock_devin.get_session.return_value = {
            "session_id": "sess-5",
            "status": "running",
            "status_detail": "working",
            "pull_requests": [],
        }
        mock_github = AsyncMock()

        updates = await check_active_sessions(devin=mock_devin, github=mock_github)

        assert len(updates) == 0

        logs = await db.list_session_logs(issue_id=5)
        assert logs[0]["status"] == "running"
        mock_github.post_issue_comment.assert_not_called()

    async def test_handles_api_failure_gracefully(self):
        """If the Devin API call fails for one session, others are still processed."""
        await db.upsert_issue(6, issue_node_id="I_6", status="planning")
        await db.upsert_issue(7, issue_node_id="I_7", status="building")
        await db.insert_session_log(6, "sess-6", "planner")
        await db.insert_session_log(7, "sess-7", "builder")

        mock_devin = AsyncMock()

        async def side_effect(session_id):
            if session_id == "sess-6":
                raise Exception("Network error")
            return {
                "session_id": "sess-7",
                "status": "running",
                "status_detail": "finished",
                "pull_requests": [],
            }

        mock_devin.get_session.side_effect = side_effect
        mock_github = AsyncMock()

        updates = await check_active_sessions(devin=mock_devin, github=mock_github)

        # sess-6 failed to poll, sess-7 was updated
        assert len(updates) == 1
        assert updates[0]["session_id"] == "sess-7"

    async def test_multiple_active_sessions(self):
        """Multiple active sessions are all polled and updated."""
        await db.upsert_issue(8, issue_node_id="I_8", status="planning")
        await db.upsert_issue(9, issue_node_id="I_9", status="building")
        await db.insert_session_log(8, "sess-8", "planner")
        await db.insert_session_log(9, "sess-9", "builder")

        mock_devin = AsyncMock()
        mock_devin.get_session.return_value = {
            "session_id": "any",
            "status": "exit",
            "status_detail": "",
            "pull_requests": [],
        }
        mock_github = AsyncMock()

        updates = await check_active_sessions(devin=mock_devin, github=mock_github)

        assert len(updates) == 2
        assert mock_devin.get_session.call_count == 2
        assert mock_github.post_issue_comment.call_count == 2

    async def test_comment_failure_does_not_break_tracking(self):
        """If posting a comment fails, the session is still tracked."""
        await db.upsert_issue(10, issue_node_id="I_10", status="planning")
        await db.insert_session_log(10, "sess-10", "planner")

        mock_devin = AsyncMock()
        mock_devin.get_session.return_value = {
            "session_id": "sess-10",
            "status": "running",
            "status_detail": "finished",
            "pull_requests": [],
        }
        mock_github = AsyncMock()
        mock_github.post_issue_comment.side_effect = Exception("GitHub down")

        updates = await check_active_sessions(devin=mock_devin, github=mock_github)

        assert len(updates) == 1
        assert updates[0]["final_status"] == "completed"
        logs = await db.list_session_logs(issue_id=10)
        assert logs[0]["status"] == "completed"

    async def test_superseded_session_marked_completed(self):
        """A planner session that is still 'running' in the Devin API but whose
        issue has already moved to 'building' should be marked completed."""
        await db.upsert_issue(11, issue_node_id="I_11", status="building")
        await db.insert_session_log(11, "sess-11", "planner")

        mock_devin = AsyncMock()
        mock_devin.get_session.return_value = {
            "session_id": "sess-11",
            "status": "running",
            "status_detail": "blocked",
            "pull_requests": [],
        }
        mock_github = AsyncMock()

        updates = await check_active_sessions(devin=mock_devin, github=mock_github)

        assert len(updates) == 1
        assert updates[0]["session_id"] == "sess-11"
        assert updates[0]["final_status"] == "completed"

        logs = await db.list_session_logs(issue_id=11)
        assert logs[0]["status"] == "completed"

    async def test_non_superseded_session_stays_running(self):
        """A planner session whose issue is still at 'planning' should NOT
        be marked completed even if the Devin API says 'blocked'."""
        await db.upsert_issue(12, issue_node_id="I_12", status="planning")
        await db.insert_session_log(12, "sess-12", "planner")

        mock_devin = AsyncMock()
        mock_devin.get_session.return_value = {
            "session_id": "sess-12",
            "status": "running",
            "status_detail": "blocked",
            "pull_requests": [],
        }
        mock_github = AsyncMock()

        updates = await check_active_sessions(devin=mock_devin, github=mock_github)

        assert len(updates) == 0
        logs = await db.list_session_logs(issue_id=12)
        assert logs[0]["status"] == "running"


class TestBuildStatusComment:
    def test_completed_planner(self):
        update = {
            "session_id": "sess-1",
            "session_type": "planner",
            "final_status": "completed",
            "duration_seconds": 180,
        }
        comment = _build_status_comment(update)
        assert "Planner" in comment
        assert "completed" in comment
        assert "3m" in comment

    def test_completed_builder_with_pr(self):
        update = {
            "session_id": "sess-2",
            "session_type": "builder",
            "final_status": "completed",
            "duration_seconds": 300,
            "pr_url": "https://github.com/org/repo/pull/5",
        }
        comment = _build_status_comment(update)
        assert "Builder" in comment
        assert "https://github.com/org/repo/pull/5" in comment

    def test_failed_session(self):
        update = {
            "session_id": "sess-3",
            "session_type": "builder",
            "final_status": "failed",
            "duration_seconds": 60,
            "api_status": "error",
        }
        comment = _build_status_comment(update)
        assert "failed" in comment
        assert "`error`" in comment
