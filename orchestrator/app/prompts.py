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

Output: A PR URL posted as an issue comment.\
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

Output: Review comments on the PR. Final status: approved or changes_requested.\
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
