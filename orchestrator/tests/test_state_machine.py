"""Tests for the state machine — transitions, validation, DB updates.

The state machine now receives issue data directly from the webhook
payload (label-based trigger) instead of resolving via GraphQL.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app import db
from app.state_machine import handle_status_change, is_valid_transition

# Shared issue kwargs used across tests — mirrors a real webhook payload.
_ISSUE_KWARGS = {
    "issue_title": "Test Issue",
    "issue_body": "Fix this bug",
    "issue_url": "https://github.com/victorlga/superset/issues/42",
    "issue_node_id": "I_node_1",
}


class TestIsValidTransition:
    def test_backlog_to_planning(self):
        assert is_valid_transition("backlog", "planning") is True

    def test_planning_to_building(self):
        assert is_valid_transition("planning", "building") is True

    def test_building_to_reviewing(self):
        assert is_valid_transition("building", "reviewing") is True

    def test_reviewing_to_done(self):
        assert is_valid_transition("reviewing", "done") is True

    def test_any_to_error(self):
        for status in ("backlog", "planning", "building", "reviewing"):
            assert is_valid_transition(status, "error") is True

    def test_skip_not_allowed(self):
        assert is_valid_transition("backlog", "building") is False

    def test_backward_not_allowed(self):
        assert is_valid_transition("building", "planning") is False

    def test_done_to_anything_not_allowed(self):
        assert is_valid_transition("done", "backlog") is False
        assert is_valid_transition("done", "planning") is False


class TestHandleStatusChange:
    @pytest.fixture
    def mock_devin(self):
        dv = AsyncMock()
        dv.create_session.return_value = {"session_id": "sess-abc123"}
        return dv

    @pytest.mark.asyncio
    async def test_planning_creates_planner_session(self, mock_devin):
        result = await handle_status_change(
            issue_number=42,
            new_status="Planning",
            devin=mock_devin,
            **_ISSUE_KWARGS,
        )

        assert result["action"] == "transitioned"
        assert result["new_status"] == "planning"
        assert result["session_id"] == "sess-abc123"
        mock_devin.create_session.assert_called_once()

        # Verify DB was updated
        issue = await db.get_issue(42)
        assert issue is not None
        assert issue["status"] == "planning"
        assert issue["planner_session"] == "sess-abc123"

    @pytest.mark.asyncio
    async def test_building_creates_builder_session(self, mock_devin):
        # Seed existing issue in planning state
        await db.upsert_issue(42, issue_node_id="I_node_1", status="planning")

        result = await handle_status_change(
            issue_number=42,
            new_status="Building",
            devin=mock_devin,
            **_ISSUE_KWARGS,
        )

        assert result["action"] == "transitioned"
        assert result["new_status"] == "building"
        mock_devin.create_session.assert_called_once()

        issue = await db.get_issue(42)
        assert issue["status"] == "building"
        assert issue["builder_session"] == "sess-abc123"

    @pytest.mark.asyncio
    async def test_reviewing_creates_reviewer_session(self, mock_devin):
        await db.upsert_issue(42, issue_node_id="I_node_1", status="building")

        result = await handle_status_change(
            issue_number=42,
            new_status="Reviewing",
            devin=mock_devin,
            **_ISSUE_KWARGS,
        )

        assert result["action"] == "transitioned"
        assert result["new_status"] == "reviewing"
        mock_devin.create_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_done_logs_completion(self, mock_devin):
        await db.upsert_issue(42, issue_node_id="I_node_1", status="reviewing")

        result = await handle_status_change(
            issue_number=42,
            new_status="Done",
            devin=mock_devin,
            **_ISSUE_KWARGS,
        )

        assert result["action"] == "transitioned"
        assert result["new_status"] == "done"
        mock_devin.create_session.assert_not_called()

        issue = await db.get_issue(42)
        assert issue["status"] == "done"
        assert issue["done_at"] is not None

    @pytest.mark.asyncio
    async def test_invalid_transition_rejected(self, mock_devin):
        await db.upsert_issue(42, issue_node_id="I_node_1", status="backlog")

        result = await handle_status_change(
            issue_number=42,
            new_status="Building",
            devin=mock_devin,
            **_ISSUE_KWARGS,
        )

        assert result["action"] == "rejected"
        assert result["reason"] == "invalid_transition"
        mock_devin.create_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_devin_api_failure_sets_error(self):
        dv = AsyncMock()
        dv.create_session.side_effect = Exception("API unreachable")

        result = await handle_status_change(
            issue_number=42,
            new_status="Planning",
            devin=dv,
            **_ISSUE_KWARGS,
        )

        assert result["action"] == "error"
        issue = await db.get_issue(42)
        assert issue["status"] == "error"
        assert "planner" in issue["error_message"].lower()

    @pytest.mark.asyncio
    async def test_session_log_created(self, mock_devin):
        result = await handle_status_change(
            issue_number=42,
            new_status="Planning",
            devin=mock_devin,
            **_ISSUE_KWARGS,
        )

        logs = await db.list_session_logs(issue_id=42)
        assert len(logs) == 1
        assert logs[0]["session_type"] == "planner"
        assert logs[0]["session_id"] == "sess-abc123"
        assert logs[0]["status"] == "running"

    @pytest.mark.asyncio
    async def test_new_issue_defaults_to_backlog(self, mock_devin):
        """An issue not yet in the DB should be treated as being in backlog."""
        result = await handle_status_change(
            issue_number=99,
            new_status="planning",
            devin=mock_devin,
            issue_title="New issue",
            issue_body="Body",
            issue_url="https://github.com/victorlga/superset/issues/99",
            issue_node_id="I_node_99",
        )
        assert result["action"] == "transitioned"
        assert result["old_status"] == "backlog"
        assert result["new_status"] == "planning"
