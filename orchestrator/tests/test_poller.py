"""Tests for the polling-based state machine driver."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app import db
from app.poller import extract_state_from_labels, poll_once


# ---------------------------------------------------------------------------
# extract_state_from_labels unit tests
# ---------------------------------------------------------------------------


class TestExtractStateFromLabels:
    def test_single_planning_label(self):
        labels = [{"name": "remediation-target"}, {"name": "state:planning"}]
        assert extract_state_from_labels(labels) == "planning"

    def test_single_building_label(self):
        labels = [{"name": "state:building"}]
        assert extract_state_from_labels(labels) == "building"

    def test_single_reviewing_label(self):
        labels = [{"name": "state:reviewing"}]
        assert extract_state_from_labels(labels) == "reviewing"

    def test_single_done_label(self):
        labels = [{"name": "state:done"}]
        assert extract_state_from_labels(labels) == "done"

    def test_no_state_label_returns_none(self):
        labels = [{"name": "remediation-target"}, {"name": "bug"}]
        assert extract_state_from_labels(labels) is None

    def test_empty_labels_returns_none(self):
        assert extract_state_from_labels([]) is None

    def test_case_insensitive(self):
        labels = [{"name": "State:Planning"}]
        assert extract_state_from_labels(labels) == "planning"

    def test_unknown_state_returns_none(self):
        labels = [{"name": "state:unknown"}]
        assert extract_state_from_labels(labels) is None

    def test_multiple_state_labels_picks_most_advanced(self):
        labels = [{"name": "state:planning"}, {"name": "state:building"}]
        assert extract_state_from_labels(labels) == "building"

    def test_multiple_state_labels_done_wins(self):
        labels = [
            {"name": "state:planning"},
            {"name": "state:reviewing"},
            {"name": "state:done"},
        ]
        assert extract_state_from_labels(labels) == "done"


# ---------------------------------------------------------------------------
# poll_once integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPollOnce:
    async def test_triggers_transition_for_new_issue(self):
        """An issue with state:planning that isn't in the DB should trigger planning."""
        mock_github = AsyncMock()
        mock_github.list_issues_with_labels.return_value = [
            {
                "number": 1,
                "title": "Session cookies not invalidated",
                "body": "After logout, cookies still work.",
                "html_url": "https://github.com/victorlga/superset/issues/1",
                "node_id": "I_node_1",
                "labels": [
                    {"name": "remediation-target"},
                    {"name": "state:planning"},
                ],
            }
        ]

        mock_devin = AsyncMock()
        mock_devin.create_session.return_value = {"session_id": "sess-poll-1"}

        actions = await poll_once(github=mock_github, devin=mock_devin)

        assert len(actions) == 1
        assert actions[0]["action"] == "transitioned"
        assert actions[0]["new_status"] == "planning"
        mock_devin.create_session.assert_called_once()

    async def test_skips_issue_already_in_sync(self):
        """An issue whose DB state matches label state should be skipped."""
        await db.upsert_issue(1, issue_node_id="I_node_1", status="planning")

        mock_github = AsyncMock()
        mock_github.list_issues_with_labels.return_value = [
            {
                "number": 1,
                "title": "Test",
                "body": "",
                "html_url": "https://github.com/victorlga/superset/issues/1",
                "node_id": "I_node_1",
                "labels": [
                    {"name": "remediation-target"},
                    {"name": "state:planning"},
                ],
            }
        ]

        mock_devin = AsyncMock()
        actions = await poll_once(github=mock_github, devin=mock_devin)

        assert len(actions) == 0
        mock_devin.create_session.assert_not_called()

    async def test_skips_issue_without_state_label(self):
        """An issue with only remediation-target (no state:*) is skipped."""
        mock_github = AsyncMock()
        mock_github.list_issues_with_labels.return_value = [
            {
                "number": 2,
                "title": "No state",
                "body": "",
                "html_url": "https://github.com/victorlga/superset/issues/2",
                "node_id": "I_node_2",
                "labels": [{"name": "remediation-target"}],
            }
        ]

        mock_devin = AsyncMock()
        actions = await poll_once(github=mock_github, devin=mock_devin)

        assert len(actions) == 0

    async def test_handles_github_api_failure(self):
        """If the GitHub API call fails, poll_once returns empty list."""
        mock_github = AsyncMock()
        mock_github.list_issues_with_labels.side_effect = Exception("API down")

        actions = await poll_once(github=mock_github)
        assert len(actions) == 0

    async def test_multiple_issues_triggers_multiple_transitions(self):
        """Multiple issues with different states each trigger their own transition."""
        await db.upsert_issue(10, issue_node_id="I_10", status="planning")

        mock_github = AsyncMock()
        mock_github.list_issues_with_labels.return_value = [
            {
                "number": 10,
                "title": "Issue 10",
                "body": "",
                "html_url": "https://github.com/victorlga/superset/issues/10",
                "node_id": "I_10",
                "labels": [
                    {"name": "remediation-target"},
                    {"name": "state:building"},
                ],
            },
            {
                "number": 11,
                "title": "Issue 11",
                "body": "",
                "html_url": "https://github.com/victorlga/superset/issues/11",
                "node_id": "I_11",
                "labels": [
                    {"name": "remediation-target"},
                    {"name": "state:planning"},
                ],
            },
        ]

        mock_devin = AsyncMock()
        mock_devin.create_session.return_value = {"session_id": "sess-multi"}

        actions = await poll_once(github=mock_github, devin=mock_devin)

        assert len(actions) == 2
        assert mock_devin.create_session.call_count == 2

    async def test_invalid_transition_returns_rejected(self):
        """If the label state is an invalid transition, result is 'rejected'."""
        # Issue is in backlog, but label says building (skipping planning)
        mock_github = AsyncMock()
        mock_github.list_issues_with_labels.return_value = [
            {
                "number": 5,
                "title": "Skip issue",
                "body": "",
                "html_url": "https://github.com/victorlga/superset/issues/5",
                "node_id": "I_5",
                "labels": [
                    {"name": "remediation-target"},
                    {"name": "state:building"},
                ],
            }
        ]

        mock_devin = AsyncMock()
        actions = await poll_once(github=mock_github, devin=mock_devin)

        assert len(actions) == 1
        assert actions[0]["action"] == "rejected"
        assert actions[0]["reason"] == "invalid_transition"
        mock_devin.create_session.assert_not_called()
