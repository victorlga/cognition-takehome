"""Tests for the database layer."""

from __future__ import annotations

import pytest

from app import db


@pytest.mark.asyncio
class TestIssueState:
    async def test_upsert_new_issue(self):
        await db.upsert_issue(1, issue_node_id="I_1", title="Bug 1", status="backlog")
        issue = await db.get_issue(1)
        assert issue is not None
        assert issue["title"] == "Bug 1"
        assert issue["status"] == "backlog"

    async def test_upsert_existing_issue(self):
        await db.upsert_issue(1, issue_node_id="I_1", status="backlog")
        await db.upsert_issue(1, status="planning")
        issue = await db.get_issue(1)
        assert issue["status"] == "planning"

    async def test_get_nonexistent_issue(self):
        assert await db.get_issue(999) is None


@pytest.mark.asyncio
class TestSessionLog:
    async def test_insert_and_list(self):
        await db.upsert_issue(1, issue_node_id="I_1", status="planning")
        log_id = await db.insert_session_log(1, "sess-1", "planner")
        assert log_id is not None

        logs = await db.list_session_logs(issue_id=1)
        assert len(logs) == 1
        assert logs[0]["session_id"] == "sess-1"
        assert logs[0]["session_type"] == "planner"
        assert logs[0]["status"] == "running"

    async def test_update_session_log(self):
        await db.upsert_issue(1, issue_node_id="I_1", status="planning")
        await db.insert_session_log(1, "sess-1", "planner")
        await db.update_session_log("sess-1", "completed", duration_seconds=120)

        logs = await db.list_session_logs(issue_id=1)
        assert logs[0]["status"] == "completed"
        assert logs[0]["duration_seconds"] == 120
        assert logs[0]["finished_at"] is not None

    async def test_list_all_session_logs(self):
        await db.upsert_issue(1, issue_node_id="I_1", status="planning")
        await db.upsert_issue(2, issue_node_id="I_2", status="building")
        await db.insert_session_log(1, "sess-1", "planner")
        await db.insert_session_log(2, "sess-2", "builder")

        logs = await db.list_session_logs()
        assert len(logs) == 2


@pytest.mark.asyncio
class TestMetrics:
    async def test_metrics_empty_db(self):
        metrics = await db.get_metrics()
        assert metrics["total_issues"] == 0
        assert metrics["active_sessions"] == 0
        # All statuses should be present with 0 counts
        assert metrics["issues"]["backlog"] == 0
        assert metrics["issues"]["done"] == 0
        # Velocity metrics should be None/0 with no data
        assert metrics["median_time_to_remediation_hours"] is None
        assert metrics["session_success_rate"] == 0.0
        assert metrics["error_rate"] == 0.0
        assert metrics["recent_activity"] == []

    async def test_metrics_with_data(self):
        await db.upsert_issue(1, issue_node_id="I_1", status="backlog")
        await db.upsert_issue(2, issue_node_id="I_2", status="planning")
        await db.upsert_issue(3, issue_node_id="I_3", status="planning")
        await db.insert_session_log(2, "sess-1", "planner", status="running")
        await db.insert_session_log(3, "sess-2", "planner", status="completed")

        metrics = await db.get_metrics()
        assert metrics["total_issues"] == 3
        assert metrics["issues"]["backlog"] == 1
        assert metrics["issues"]["planning"] == 2
        assert metrics["active_sessions"] == 1
        assert len(metrics["recent_activity"]) == 2
        # Velocity metrics
        assert metrics["total_sessions"] == 2
        assert metrics["completed_sessions"] == 1
        assert metrics["failed_sessions"] == 0
        assert metrics["session_success_rate"] == 0.5
        assert metrics["error_rate"] == 0.0
        # Risk posture
        assert "severity_breakdown" in metrics
        assert "open_trend" in metrics
        assert "closed_trend" in metrics
