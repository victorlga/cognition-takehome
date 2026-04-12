"""Tests for prompt template rendering."""

from app.prompts import (
    IssueContext,
    build_builder_prompt,
    build_planner_prompt,
    build_rebuild_prompt,
    build_reviewer_prompt,
)


def _make_ctx(**overrides) -> IssueContext:
    defaults = {
        "issue_url": "https://github.com/victorlga/superset/issues/42",
        "issue_title": "XSS in SQL Lab",
        "issue_body": "Unsanitised user input in the SQL editor.",
        "issue_number": 42,
    }
    defaults.update(overrides)
    return IssueContext(**defaults)


class TestPlannerPrompt:
    def test_contains_issue_url(self):
        ctx = _make_ctx()
        prompt = build_planner_prompt(ctx)
        assert ctx.issue_url in prompt

    def test_contains_issue_title(self):
        ctx = _make_ctx()
        prompt = build_planner_prompt(ctx)
        assert ctx.issue_title in prompt

    def test_contains_issue_body(self):
        ctx = _make_ctx()
        prompt = build_planner_prompt(ctx)
        assert ctx.issue_body in prompt

    def test_contains_repo_name(self):
        prompt = build_planner_prompt(_make_ctx())
        assert "victorlga/superset" in prompt

    def test_contains_instructions(self):
        prompt = build_planner_prompt(_make_ctx())
        assert "remediation plan" in prompt.lower()


class TestBuilderPrompt:
    def test_contains_plan_text(self):
        plan = "Step 1: fix the sanitiser\nStep 2: add a test"
        prompt = build_builder_prompt(_make_ctx(), plan)
        assert plan in prompt

    def test_contains_issue_url(self):
        ctx = _make_ctx()
        prompt = build_builder_prompt(ctx, "some plan")
        assert ctx.issue_url in prompt

    def test_contains_branch_with_issue_number(self):
        ctx = _make_ctx(issue_number=99)
        prompt = build_builder_prompt(ctx, "plan")
        assert "fix/99" in prompt


class TestReviewerPrompt:
    def test_contains_pr_url(self):
        pr = "https://github.com/victorlga/superset/pull/7"
        prompt = build_reviewer_prompt(_make_ctx(), pr)
        assert pr in prompt

    def test_contains_issue_url(self):
        ctx = _make_ctx()
        prompt = build_reviewer_prompt(ctx, "https://pr")
        assert ctx.issue_url in prompt

    def test_contains_security_review_instruction(self):
        prompt = build_reviewer_prompt(_make_ctx(), "https://pr")
        assert "security" in prompt.lower()


class TestRebuildPrompt:
    def test_contains_pr_url(self):
        pr = "https://github.com/victorlga/superset/pull/5"
        prompt = build_rebuild_prompt(_make_ctx(), pr, "Fix tests", 1)
        assert pr in prompt

    def test_contains_review_feedback(self):
        feedback = "Three tests are failing in test_security.py"
        prompt = build_rebuild_prompt(_make_ctx(), "https://pr", feedback, 1)
        assert feedback in prompt

    def test_contains_rebuild_count(self):
        prompt = build_rebuild_prompt(_make_ctx(), "https://pr", "feedback", 2)
        assert "2" in prompt

    def test_contains_issue_url(self):
        ctx = _make_ctx()
        prompt = build_rebuild_prompt(ctx, "https://pr", "feedback", 1)
        assert ctx.issue_url in prompt

    def test_instructs_to_fix(self):
        prompt = build_rebuild_prompt(_make_ctx(), "https://pr", "feedback", 1)
        assert "fix" in prompt.lower() or "address" in prompt.lower()
