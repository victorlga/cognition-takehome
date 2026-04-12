"""Prompt templates for Devin sessions (planner / builder / reviewer)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IssueContext:
    """Minimal issue context needed to build prompts."""

    issue_url: str
    issue_title: str
    issue_body: str
    issue_number: int


PLANNER_TEMPLATE = """\
You are a security engineer. Analyze the following GitHub issue and produce a remediation plan.

Issue: {issue_url}
Title: {issue_title}
Body:
{issue_body}

Repository: victorlga/superset (fork of apache/superset)

Instructions:
1. Read the issue carefully. Identify the root cause.
2. Search the codebase for affected files.
3. Write a step-by-step remediation plan (max 10 steps).
4. For each step, specify: file path, what changes, why.
5. Identify test files that need updating or new tests to write.
6. Post the plan as a comment on the issue.

Note: The orchestrator automatically tracks session status and updates issue labels.
Focus on delivering the plan content — status tracking is handled externally.

Output: A structured remediation plan posted as an issue comment.\
"""

BUILDER_TEMPLATE = """\
You are a senior engineer. Implement the approved remediation plan for this issue.

Issue: {issue_url}
Approved Plan:
{plan_text}

Repository: victorlga/superset
Branch: fix/{issue_number}-remediation

Instructions:
1. Create a feature branch from main.
2. Implement each step of the plan.
3. Write or update tests to cover the fix.
4. Run the relevant test suite to verify.
5. Open a PR against main with a clear description.

Note: The orchestrator automatically posts the PR URL and status updates on the
issue thread. Focus on the implementation — do not post duplicate status comments.

Output: A pull request opened against main.\
"""

REVIEWER_TEMPLATE = """\
You are a code reviewer specializing in security. Review this PR.

PR: {pr_url}
Related Issue: {issue_url}

Instructions:
1. Review the diff for correctness, security, and style.
2. Run the test suite. If tests fail, leave review comments.
3. If changes are needed, leave specific inline comments.
4. If the PR is ready, approve it.

Note: The orchestrator automatically tracks review status and updates issue labels.
Focus on the code review — status tracking is handled externally.

Output: Review comments on the PR. Final status: approved or changes_requested.\
"""

REBUILD_TEMPLATE = """\
You are a senior engineer. A code reviewer found problems with a PR. Fix them.

PR: {pr_url}
Related Issue: {issue_url}
Rebuild attempt: {rebuild_count}

Reviewer Feedback:
{review_feedback}

Repository: victorlga/superset

Instructions:
1. Check out the existing PR branch — do NOT create a new branch.
2. Read the reviewer's feedback carefully.
3. Address every issue raised by the reviewer (failing tests, security gaps, style nits).
4. Run the relevant test suite to verify your fixes.
5. Push your changes to the same PR branch.

Note: The orchestrator automatically posts status updates on the issue thread.
Focus on fixing the reviewer's findings — do not post duplicate status comments.

Output: Updated commits pushed to the existing PR branch.\
"""


def build_planner_prompt(issue: IssueContext) -> str:
    """Build the planner session prompt."""
    return PLANNER_TEMPLATE.format(
        issue_url=issue.issue_url,
        issue_title=issue.issue_title,
        issue_body=issue.issue_body,
    )


def build_builder_prompt(issue: IssueContext, plan_text: str) -> str:
    """Build the builder session prompt."""
    return BUILDER_TEMPLATE.format(
        issue_url=issue.issue_url,
        plan_text=plan_text,
        issue_number=issue.issue_number,
    )


def build_reviewer_prompt(issue: IssueContext, pr_url: str) -> str:
    """Build the reviewer session prompt."""
    return REVIEWER_TEMPLATE.format(
        pr_url=pr_url,
        issue_url=issue.issue_url,
    )


def build_rebuild_prompt(
    issue: IssueContext, pr_url: str, review_feedback: str, rebuild_count: int,
) -> str:
    """Build the rebuild builder prompt with reviewer feedback."""
    return REBUILD_TEMPLATE.format(
        pr_url=pr_url,
        issue_url=issue.issue_url,
        review_feedback=review_feedback,
        rebuild_count=rebuild_count,
    )
