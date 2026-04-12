# Vulnerability Remediation Orchestrator — Technical Report

## Overview

This system automates the vulnerability remediation lifecycle by orchestrating AI-powered Devin sessions through a multi-stage pipeline. It monitors GitHub issues labeled `remediation-target`, drives them through planning, building, and reviewing stages via Devin API sessions, and provides an observability dashboard for tracking progress.

---

## Architecture

```
GitHub Issues (state:* labels)
       |
       v
  +---------+       +----------------+       +-----------+
  | Poller  | ----> | State Machine  | ----> | Devin API |
  | (30s)   |       | (transitions)  |       | (sessions)|
  +---------+       +----------------+       +-----------+
       |                    |                       |
       v                    v                       v
  +-----------+       +-----------+          +-------------+
  | GitHub    |       | SQLite DB |  <-----  | Session     |
  | API       |       | (state)   |          | Tracker     |
  +-----------+       +-----------+          | (30s poll)  |
                            |                +-------------+
                            v
                      +-----------+
                      | Dashboard |
                      | (htmx)    |
                      +-----------+
```

**Core components:**

| Component | File | Role |
|-----------|------|------|
| Poller | `orchestrator/app/poller.py` | Polls GitHub issues every 30s, detects label-vs-DB state mismatches |
| State Machine | `orchestrator/app/state_machine.py` | Validates transitions, creates Devin sessions, updates DB and labels |
| Session Tracker | `orchestrator/app/session_tracker.py` | Polls active Devin sessions, handles completion, triggers rebuilds |
| Devin Client | `orchestrator/app/devin_client.py` | Async wrapper for Devin API v3 |
| GitHub Client | `orchestrator/app/github_client.py` | Async wrapper for GitHub REST API |
| Database | `orchestrator/app/db.py` | SQLite via aiosqlite, two tables |
| Dashboard | `orchestrator/app/dashboard.py` | FastAPI routes + Jinja2/htmx/Chart.js UI |
| Prompts | `orchestrator/app/prompts.py` | Template builders for each session type |
| Config | `orchestrator/app/config.py` | Pydantic BaseSettings from env vars |
| Entry Point | `orchestrator/app/main.py` | FastAPI app with async lifespan (starts poller + tracker) |

---

## State Machine

### Pipeline States

```
backlog --> planning --> building --> reviewing --> done
                            ^            |
                            |            | (changes_requested)
                            +------------+
                          (rebuild loop)

Any state ---> error  (on exception)
```

### Valid Transitions

| From | To | Trigger |
|------|----|---------|
| `backlog` | `planning` | `state:planning` label added to issue |
| `planning` | `building` | `state:building` label added |
| `building` | `reviewing` | `state:reviewing` label added |
| `reviewing` | `done` | `state:done` label added |
| `reviewing` | `building` | Auto-triggered when reviewer posts `CHANGES_REQUESTED` |
| Any | `error` | Unhandled exception or rebuild cap exceeded |

### Transition Mechanics

Each transition follows this sequence in `handle_status_change()`:

1. **Validate** — `is_valid_transition(old, new)` rejects illegal jumps
2. **Finalize previous session** — marks the prior stage's Devin session as `completed` in `session_log`
3. **Create new Devin session** — with stage-appropriate prompt and tags
4. **Upsert DB** — updates `issue_state` with new status, session ID, and timestamp
5. **Sync GitHub label** — removes old `state:*` labels, adds new one

### Session Finalization Map

| Entering State | Finalizes Session From |
|----------------|----------------------|
| `planning` | — (no prior session) |
| `building` | `planner_session` |
| `reviewing` | `builder_session` |
| `done` | `reviewer_session` |
| `building` (rebuild) | `reviewer_session` |

---

## Devin Session Types

### Planner
- **Tags:** `["issue-{N}", "planner"]`
- **Prompt:** `build_planner_prompt(issue)` — analyzes the vulnerability, researches the codebase, posts a remediation plan as an issue comment
- **Output:** Plan text posted to GitHub issue

### Builder
- **Tags:** `["issue-{N}", "builder"]`
- **Prompt:** `build_builder_prompt(issue, plan_text)` — implements the plan, writes tests, opens a PR
- **Output:** Pull request URL (extracted from `pull_requests` in Devin response)

### Reviewer
- **Tags:** `["issue-{N}", "reviewer"]`
- **Prompt:** `build_reviewer_prompt(issue, pr_url)` — reviews the PR, approves or requests changes
- **Output:** GitHub PR review (APPROVED or CHANGES_REQUESTED)

### Rebuild (Builder variant)
- **Tags:** `["issue-{N}", "builder", "rebuild"]`
- **Prompt:** `build_rebuild_prompt(issue, pr_url, review_feedback, rebuild_count)` — addresses reviewer feedback, pushes fixes to same PR branch
- **Output:** Updated PR

---

## Background Loops

### Poller (`poller.py`)

Runs every `poll_interval_seconds` (default 30s):

1. Fetch all open issues with `remediation-target` label from GitHub
2. For each issue, extract the `state:*` label (highest-priority wins if multiple exist)
3. Compare label-derived state against DB state
4. If different and transition is valid, call `handle_status_change()`
5. Exceptions are caught and logged — the loop never crashes

**Label priority order:** `done` > `reviewing` > `building` > `planning`

### Session Tracker (`session_tracker.py`)

Runs every `poll_interval_seconds` (default 30s):

1. Query all `session_log` rows with `status='running'`
2. For each session, call Devin API to check status
3. Terminal conditions: status in `{exit, error, suspended}` or `status_detail == 'finished'`
4. On completion:
   - Compute duration, set `finished_at`
   - Extract PR URL for builder sessions
   - Post audit-trail comment on the GitHub issue
   - **If reviewer session completed with `CHANGES_REQUESTED`:** trigger auto-rebuild
5. **Supersession check:** if the issue has advanced past this session's expected stage, mark it completed regardless

---

## Auto-Rebuild Loop

When a reviewer session completes (`session_tracker.py`):

1. Check if issue is still in `reviewing` state
2. Fetch PR reviews from GitHub API
3. Look for `CHANGES_REQUESTED` review (skip if a later `APPROVED` exists)
4. If changes were requested:
   - Collect review feedback (review bodies + inline file comments)
   - Format as markdown
   - Call `handle_status_change(new_status='building', review_feedback=...)`
   - This creates a new builder session with the feedback baked into the prompt
5. `rebuild_count` is incremented; if it exceeds `max_rebuild_attempts` (default 3), the issue moves to `error`

---

## Database Schema

**Engine:** SQLite via aiosqlite  
**Path:** `./data/orchestrator.db`

### `issue_state`

| Column | Type | Purpose |
|--------|------|---------|
| `issue_id` | INTEGER PK | GitHub issue number |
| `issue_node_id` | TEXT | GitHub GraphQL node ID |
| `title` | TEXT | Issue title |
| `category` | TEXT | `security` / `high-impact-bug` / `dependency` / `sast` |
| `status` | TEXT | Current pipeline state |
| `planner_session` | TEXT | Devin session ID for planning |
| `builder_session` | TEXT | Devin session ID for building |
| `reviewer_session` | TEXT | Devin session ID for reviewing |
| `plan_text` | TEXT | Cached remediation plan |
| `pr_url` | TEXT | Pull request URL (set by builder) |
| `created_at` | TEXT | ISO-8601 creation timestamp |
| `updated_at` | TEXT | ISO-8601 last update timestamp |
| `planning_started_at` | TEXT | Timestamp entering planning |
| `building_started_at` | TEXT | Timestamp entering building |
| `reviewing_started_at` | TEXT | Timestamp entering reviewing |
| `done_at` | TEXT | Timestamp entering done |
| `rebuild_count` | INTEGER | Number of rebuild attempts (capped at 3) |
| `error_message` | TEXT | Error details if failed |

### `session_log`

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK | Auto-incremented |
| `issue_id` | INTEGER FK | References `issue_state` |
| `session_id` | TEXT | Devin session ID |
| `session_type` | TEXT | `planner` / `builder` / `reviewer` / `scanner` |
| `status` | TEXT | `running` / `completed` / `failed` |
| `started_at` | TEXT | ISO-8601 start timestamp |
| `finished_at` | TEXT | ISO-8601 end timestamp |
| `duration_seconds` | INTEGER | Elapsed time |

---

## API Endpoints

| Method | Path | Response | Purpose |
|--------|------|----------|---------|
| GET | `/health` | `{"status": "ok"}` | Liveness probe (Docker HEALTHCHECK) |
| GET | `/dashboard` | HTML | Observability dashboard |
| GET | `/api/metrics` | JSON | Pipeline stats, session health, activity feed |
| GET | `/api/issues` | JSON | All tracked issues with full state |

### Metrics Response Shape

```json
{
  "issues": {"backlog": 0, "planning": 0, "building": 0, "reviewing": 0, "done": 0, "error": 0},
  "total_issues": 0,
  "active_sessions": 0,
  "active_sessions_by_type": {"planner": 0, "builder": 0, "reviewer": 0},
  "session_success_rate": 0.0,
  "total_sessions": 0,
  "completed_sessions": 0,
  "failed_sessions": 0,
  "recent_activity": []
}
```

---

## Dashboard

The dashboard (`templates/dashboard.html`) provides real-time observability:

- **Summary cards:** Issues remediated, active sessions (by type), session success rate
- **Pipeline chart:** Horizontal bar chart of issue counts per state (Chart.js)
- **Activity feed:** Table of the 20 most recent session events with PR links
- **Auto-refresh:** htmx polls `/api/metrics` every 30s and updates the UI in-place

---

## Configuration

Managed via environment variables (Pydantic `BaseSettings` in `config.py`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEVIN_API_KEY` | — (required) | Devin API authentication |
| `DEVIN_ORG_ID` | — (required) | Devin organization ID |
| `GITHUB_TOKEN` | — (required) | GitHub API authentication |
| `GITHUB_REPO` | `victorlga/superset` | Target repository |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/orchestrator.db` | SQLite path |
| `POLL_INTERVAL_SECONDS` | `30` | Poller and tracker cycle interval |
| `POLLING_ENABLED` | `true` | Enable/disable polling loop |
| `MAX_REBUILD_ATTEMPTS` | `3` | Cap on reviewer-triggered rebuilds |

---

## Deployment

```yaml
# docker-compose.yml
services:
  orchestrator:
    build: ./orchestrator        # Python 3.12 + uvicorn
    ports: ["8000:8000"]
    volumes: ["./data:/app/data"] # Persistent SQLite
    restart: unless-stopped
```

- **Runtime:** Python 3.12, FastAPI, uvicorn
- **Healthcheck:** `curl http://localhost:8000/health`
- **Startup:** FastAPI lifespan initializes DB, starts poller loop + session tracker loop as asyncio background tasks
- **Shutdown:** Graceful — background tasks are cancelled on app shutdown

---

## Test Suite

Located in `orchestrator/tests/` with pytest + pytest-asyncio:

| File | Coverage |
|------|----------|
| `test_state_machine.py` | Transition validation, session creation, label sync |
| `test_poller.py` | Label extraction, poll cycle, idempotency |
| `test_session_tracker.py` | Session completion, PR extraction, rebuild triggers |
| `test_devin_client.py` | API client methods, error handling |
| `test_db.py` | CRUD operations, metrics aggregation |
| `test_prompts.py` | Prompt template generation |

---

## Key Design Decisions

1. **Polling over webhooks** — No publicly-reachable endpoint needed; simpler deployment at the cost of ~30s latency
2. **Labels as state encoding** — GitHub `state:*` labels serve as both UI and trigger mechanism; the poller reconciles label state with DB state
3. **SQLite** — Sufficient for single-instance orchestrator; no external database dependency
4. **Idempotent transitions** — `label state == DB state` check prevents duplicate session creation
5. **Supersession** — If the pipeline advances past a session's stage, the tracker marks it completed rather than waiting for Devin to finish
6. **Rebuild cap** — Prevents infinite reviewer/builder loops (default max 3 attempts)
7. **Audit trail** — Every session completion posts a summary comment on the GitHub issue
