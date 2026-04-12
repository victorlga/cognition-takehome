# Architecture — Event-Driven Vulnerability Remediation System

> **Status:** Approved (Phase 0 — Planning)
> **Last updated:** 2026-04-12

## Overview

An event-driven system that uses the **Devin API** as its core execution primitive to automatically plan, build, review, and land fixes for security vulnerabilities and high-impact bugs in [Apache Superset](https://github.com/apache/superset). The system is triggered by **issue label transitions** (`state:*` labels) and orchestrated by a lightweight FastAPI backend.

---

## System Diagram

```mermaid
flowchart TB
    subgraph GitHub ["GitHub (victorlga/superset)"]
        Issues["Issues\n(backlog items)"]
        Project["GitHub Project v2\nKanban Board"]
        PRs["Pull Requests"]
        Wiki["Fork Wiki"]
    end

    subgraph Orchestrator ["Orchestrator (FastAPI + Docker)"]
        Poller["Poller\n(background task)"]
        SM["State Machine\n(per-issue)"]
        DevinClient["Devin API Client"]
        Tracker["Session Tracker\n(background task)"]
        DB["SQLite DB\n(state + metrics)"]
        Scheduler["Periodic Scanner\n(scheduled Devin)"]
        Dashboard["Observability Dashboard\n/dashboard"]
    end

    subgraph DevinCloud ["Devin Platform"]
        PlannerSession["Planner Devin Session"]
        BuilderSession["Builder Devin Session"]
        ReviewerSession["Reviewer Devin Session"]
        ScannerSession["Scanner Devin Session"]
    end

    %% Event flow (polling is primary, webhook is optional)
    Issues -- "poll: list issues\nwith state:* labels" --> Poller
    Poller --> SM
    SM -- "Backlog → Planning" --> DevinClient
    DevinClient -- "create session\n(planner prompt)" --> PlannerSession
    PlannerSession -- "posts plan as\nissue comment" --> Issues

    SM -- "Planning → Building\n(plan approved)" --> DevinClient
    DevinClient -- "create session\n(builder prompt)" --> BuilderSession
    BuilderSession -- "opens PR" --> PRs

    SM -- "Building → Reviewing" --> DevinClient
    DevinClient -- "create session\n(reviewer prompt)" --> ReviewerSession
    ReviewerSession -- "review comments\n+ CI loop" --> PRs

    PRs -- "Reviewing → Done\n(human merge)" --> Project

    %% Session tracking (polls Devin API for active sessions)
    Tracker -- "poll active sessions" --> DevinClient
    DevinClient -- "GET /sessions/{id}" --> DevinCloud
    Tracker -- "update status,\nextract PR URLs,\npropagate errors" --> DB

    %% Periodic scan
    Scheduler -- "cron: daily" --> ScannerSession
    ScannerSession -- "files new issues" --> Issues
    Issues --> Project

    %% Observability
    SM --> DB
    DB --> Dashboard
```

---

## Tech Stack

| Component | Choice | Rationale |
|---|---|---|
| **Orchestrator** | Python 3.12 + FastAPI | Fastest path to a working async API client. Python is Superset's own language, so the reviewer audience is familiar. `httpx` for async HTTP calls. |
| **Persistence** | SQLite (via `aiosqlite`) | Zero-ops, single-file, sufficient for demo-scale state. Easily inspectable for the Loom walkthrough. |
| **Containerization** | Docker Compose | Single `docker compose up` to run the orchestrator and dashboard. Zero additional configuration needed beyond env vars. Required by the take-home spec. |
| **Polling** | Background `asyncio` task | Polls the GitHub API every N seconds for `state:*` label changes. Eliminates the need for a publicly-reachable webhook endpoint — `docker compose up` just works. |
| **Devin API** | v3 REST (`https://api.devin.ai/v3/organizations/{org_id}/`) | Latest API with RBAC, session attribution, playbook attachment, and structured polling. Endpoints include org_id in the URL path. |
| **Dashboard** | FastAPI + Jinja2 + htmx | Minimal single-page dashboard served by the same FastAPI process. No separate frontend build step. Answers "how would an engineering leader know this is working?" |
| **Scanning** | `pip-audit`, `bandit`, `semgrep`, `npm audit` | Industry-standard tools. Results feed into issue creation. |
| **GitHub CLI** | `gh` | Issue/project/PR management from Devin sessions and orchestrator scripts. |

---

## Event Flow — Detailed

### Primary Trigger: Polling-Based Label Detection

> **Design choice:** The orchestrator uses **polling** as the primary trigger instead of webhooks. This eliminates the need for a publicly-reachable URL, so `docker compose up` works out of the box with zero tunnel or deploy setup.

A background `asyncio` task polls the GitHub API every N seconds (default: 30) for open issues carrying the `remediation-target` label and any `state:*` label. For each issue, the poller extracts the state from the label name, compares it against the SQLite DB state, and fires a transition when they differ.

| Label Detected | Transition | Devin Session Type |
|---|---|---|
| `state:planning` | Backlog → Planning | **Planner**: reads the issue, researches the codebase, posts a remediation plan as an issue comment |
| `state:building` | Planning → Building | **Builder**: executes the approved plan, writes code, opens a PR |
| `state:reviewing` | Building → Reviewing | **Reviewer**: reviews the PR, runs tests, iterates with builder until CI is green |
| `state:done` | Reviewing → Done | Log completion — orchestrator records metrics |

**Polling flow:**
1. `GET /repos/{repo}/issues?labels=remediation-target&state=open` (paginated)
2. For each issue, extract `state:*` label → derive internal status
3. Compare against `issue_state.status` in SQLite
4. If different → delegate to `handle_status_change()` in the state machine
5. If same → skip (idempotent, no duplicate transitions)

Duplicate triggers are no-ops because the poller always checks the DB state before firing. The state machine itself also validates transitions (no skipping states).

### Secondary Trigger: Periodic Vulnerability Scan

A **Scheduled Devin session** (or orchestrator cron job) runs daily:
1. Clones `victorlga/superset` (latest main)
2. Runs `pip-audit`, `bandit`, `semgrep`, `npm audit`
3. Diffs findings against previously filed issues (dedup by CVE/rule ID)
4. Files new GitHub issues for net-new findings, adds them to the Project board's Backlog

This makes the "event-driven" narrative richer: the system both reacts to human-curated issues AND proactively discovers new ones.

---

## Orchestrator State Machine

Each tracked issue has a state record in SQLite:

```sql
CREATE TABLE issue_state (
    issue_id        INTEGER PRIMARY KEY,  -- GitHub issue number
    issue_node_id   TEXT NOT NULL,
    title           TEXT,
    category        TEXT NOT NULL DEFAULT 'security',  -- security|high-impact-bug|dependency|sast
    status          TEXT NOT NULL DEFAULT 'backlog',  -- backlog|planning|building|reviewing|done|error
    planner_session TEXT,       -- Devin session ID
    builder_session TEXT,
    reviewer_session TEXT,
    plan_text       TEXT,       -- cached remediation plan
    pr_url          TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    planning_started_at TEXT,   -- timestamp when moved to planning
    building_started_at TEXT,   -- timestamp when moved to building
    reviewing_started_at TEXT,  -- timestamp when moved to reviewing
    done_at         TEXT,       -- timestamp when moved to done
    error_message   TEXT
);

CREATE TABLE session_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id        INTEGER NOT NULL,
    session_id      TEXT NOT NULL,
    session_type    TEXT NOT NULL,  -- planner|builder|reviewer|scanner
    status          TEXT NOT NULL,  -- running|completed|error
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    duration_seconds INTEGER,
    FOREIGN KEY (issue_id) REFERENCES issue_state(issue_id)
);
```

---

## Devin Session Prompts (Templates)

Each session type gets a structured prompt built by the orchestrator:

### Planner Prompt (template)
```
You are a security engineer. Analyze the following GitHub issue and produce a remediation plan.

Issue: {issue_url}
Title: {issue_title}
Body: {issue_body}

Repository: victorlga/superset (fork of apache/superset)

Instructions:
1. Read the issue carefully. Identify the root cause.
2. Search the codebase for affected files.
3. Write a step-by-step remediation plan (max 10 steps).
4. For each step, specify: file path, what changes, why.
5. Identify test files that need updating or new tests to write.
6. Post the plan as a comment on the issue.

Output: A structured remediation plan posted as an issue comment.
```

### Builder Prompt (template)
```
You are a senior engineer. Implement the approved remediation plan for this issue.

Issue: {issue_url}
Approved Plan: {plan_text}

Repository: victorlga/superset
Branch: fix/{issue_number}-{slug}

Instructions:
1. Create a feature branch from main.
2. Implement each step of the plan.
3. Write or update tests to cover the fix.
4. Run the relevant test suite to verify.
5. Open a PR against main with a clear description.

Output: A PR URL posted as an issue comment.
```

### Reviewer Prompt (template)
```
You are a code reviewer specializing in security. Review this PR.

PR: {pr_url}
Related Issue: {issue_url}

Instructions:
1. Review the diff for correctness, security, and style.
2. Run the test suite. If tests fail, leave review comments.
3. If changes are needed, leave specific inline comments.
4. If the PR is ready, approve it.

Output: Review comments on the PR. Final status: approved or changes_requested.
```

---

## Observability

The dashboard (served at `/dashboard` by the FastAPI app) answers the VP-of-Engineering question: **"How do I know this is working?"**

### Metrics — What a VP of Engineering Wants to See

**Pipeline Health ("Is the system working right now?")**
- **Active Devin Sessions** — count of running planner/builder/reviewer sessions, broken down by type. Answers: "How busy is the system?"
- **Issues by Status** — bar chart: backlog / planning / building / reviewing / done / error. Answers: "Where are things stuck?" A pile-up in any column signals a bottleneck.
- **Error Rate** — % of sessions that ended in error, with most recent error messages. Answers: "Is something broken?"

**Velocity & Efficiency ("Is this worth the investment?")**
- **Time-to-Remediation (TTR)** — median and p90 time from issue entering Planning to PR merged. The headline metric. Broken down by stage (planning time, build time, review time) to show where time is spent.
- **Throughput** — issues remediated per day/week. Trend line shows whether the system is accelerating.
- **Session Success Rate** — % of Devin sessions that complete without error. Track over time to show reliability improving.
- **Devin Compute Cost per Fix** — total session-minutes / issues completed. Proxy for cost-efficiency. (Computed from `session_log.duration_seconds`.)

**Risk Posture ("Are we safer than yesterday?")**
- **Open vs. Closed Vulnerability Trend** — line chart showing cumulative issues filed vs. issues remediated over time. The gap should be shrinking.
- **Severity Breakdown** — issues by category (security / high-impact bug / dependency / SAST). Shows the system handles diverse risk types, not just version bumps.
- **Mean Time to First Response (MTFR)** — time from issue creation to first planner session starting. Measures how quickly the system reacts.

**Recent Activity ("What just happened?")**
- **Activity Feed** — latest 20 session events: session type, issue, status, duration, with links to PRs and issues. A VP can glance at this and understand the current state without digging.

### Implementation
- Metrics computed from SQLite on each dashboard load (demo-scale, no need for a metrics pipeline)
- Rendered via Jinja2 templates with Chart.js for visualizations
- Auto-refreshes via htmx polling every 30 seconds
- JSON API at `/api/metrics` for programmatic access
- Dashboard layout: 4 summary cards at top (TTR, throughput, success rate, active sessions), two chart rows (pipeline funnel + trend lines), activity feed at bottom

---

## Secrets

All secrets are provided via environment variables. **Never hardcode.**

| Variable | Purpose | How to Provision | Where Used |
|---|---|---|---|
| `DEVIN_API_KEY` | Devin API v3 token (from a **service user**, not the legacy API keys page) | [app.devin.ai](https://app.devin.ai) → Team Settings → Service Users → create a service user with Admin access → copy its API token | Orchestrator → Devin API |
| `DEVIN_ORG_ID` | Devin organization ID | Shown on the service user page or in any Devin API response | Orchestrator → Devin API |
| `GITHUB_TOKEN` | GitHub PAT with `repo`, `project`, `admin:org` scopes | GitHub → Settings → Developer Settings → PAT (fine-grained) | Orchestrator → GitHub API, `gh` CLI |
| `POLL_INTERVAL_SECONDS` | Polling interval in seconds (default: 30) | Set in `.env` or `docker-compose.yml` | Poller background task |
| `POLLING_ENABLED` | Enable/disable the background poller (default: true) | Set in `.env` or `docker-compose.yml` | Poller background task |

> **Note:** The legacy "API Keys" page on Devin is deprecated. Use **Service Users** instead. A service user named `takehome` with Admin access has already been created for this project.

---

## Directory Structure (Target)

```
cognition-takehome/
├── docs/
│   ├── TAKEHOME.md
│   ├── PLAN.md
│   ├── ARCHITECTURE.md
│   ├── PHASE_1.md
│   ├── PHASE_2.md
│   ├── PHASE_3.md
│   ├── PHASE_4.md
│   ├── PHASE_5.md
│   └── PHASE_6.md
├── orchestrator/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py             # FastAPI app entry
│   │   ├── config.py           # Settings / env vars
│   │   ├── poller.py           # Polling-based state machine driver (primary trigger)
│   │   ├── session_tracker.py  # Background loop: polls active Devin sessions to completion
│   │   ├── devin_client.py     # Devin API v3 wrapper
│   │   ├── github_client.py    # GitHub API helper
│   │   ├── state_machine.py    # Issue state transitions
│   │   ├── prompts.py          # Devin session prompt templates
│   │   ├── scanner.py          # Periodic vuln scan logic
│   │   ├── db.py               # SQLite models + queries
│   │   └── dashboard.py        # Dashboard routes + metrics
│   └── templates/
│       └── dashboard.html      # Jinja2 + htmx dashboard
├── docker-compose.yml
├── CHANGELOG.md
├── README.md
└── .gitignore
```

---

## Design Decisions Log

| # | Decision | Alternatives Considered | Rationale |
|---|---|---|---|
| 1 | **FastAPI** over Node/Express | Express, Hono | Python matches Superset's ecosystem; FastAPI has native async, auto-docs, Pydantic validation. Faster to ship for a solo dev in 2-3 hours. |
| 2 | **SQLite** over Postgres | Postgres, Redis | Zero-ops. Demo-scale data (< 100 rows). Single file = easy to inspect in Loom. No Docker service dependency. |
| 3 | **Polling** as primary trigger | GitHub webhooks, GitHub Projects v2 webhooks | Polling eliminates the need for a publicly-reachable URL. `docker compose up` just works — zero tunnel, zero deploy, zero webhook config. The poller checks `state:*` labels on issues via the GitHub API every N seconds. |
| 4 | **Issue labels** as state encoding | GitHub Projects v2 status field | Labels are the source of truth for pipeline state. The Projects v2 board is still used for visual kanban tracking but does not drive the state machine. Labels are readable via polling. |
| 5 | **Devin-as-primitive** for planner/builder/reviewer | Custom LLM calls, hand-written scripts | The take-home explicitly evaluates "leveraging Devin as a core primitive." Each role is a Devin session with a tailored prompt. |
| 6 | **htmx dashboard** over React SPA | React, Streamlit, Grafana | Zero build step. Serves from the same FastAPI process. htmx gives reactivity without JS complexity. |
| 7 | **Scheduled Devin** for periodic scans | Cron in orchestrator | Demonstrates another Devin API capability (scheduled sessions). Enriches the event-driven narrative. |
| 8 | **Docker Compose** for deployment | Kubernetes, bare metal | Required by take-home spec. Simple, portable, reproducible. |
