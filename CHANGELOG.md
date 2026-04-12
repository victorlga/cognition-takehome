# CHANGELOG

> **Contract:** Each entry follows this format:
>
> ## [PHASE_X] — YYYY-MM-DD — One-line summary
>
> **What changed:**
> (Bullet list of changes)
>
> **Files touched:**
> (List of files added/modified/deleted)
>
> **How it was verified:**
> (CI green, curl commands, screenshots, manual checks, etc.)
>
> **What the next phase needs to know:**
> (Key context, decisions, blockers, or artifacts that downstream phases depend on)
>
> **Open questions / known gaps:**
> (Anything unresolved that future phases should be aware of)
>
> ---
>
> **Rules:**
> - Future phases MUST read the entire CHANGELOG before starting work and decide which entries are relevant.
> - Sub-phases (e.g., PHASE_3_1, PHASE_3_2) do NOT write to CHANGELOG directly — only the parent orchestrator phase does after merging sub-phase outputs.
> - Entries are append-only. Never edit or delete a previous entry.

---

## [PHASE_0] — 2026-04-12 — Bootstrap planning docs, playbook, and machine

**What changed:**
- Created `docs/TAKEHOME.md` (verbatim from recruiter email)
- Created `docs/PLAN.md` (master plan with phase overview and dependency graph)
- Created `docs/ARCHITECTURE.md` (system architecture, tech stack, Mermaid diagram, secrets, design decisions)
- Created `docs/PHASE_1.md` through `docs/PHASE_6.md` (self-contained phase prompts)
- Created `CHANGELOG.md` (this file, with contract documented)
- Created Devin Playbook `cognition-takehome-prompting-playbook` via native Devin Playbook feature
- Configured Devin Machine with both repos and required tooling

**Files touched:**
- `docs/TAKEHOME.md` (already existed)
- `docs/PLAN.md` (new)
- `docs/ARCHITECTURE.md` (new)
- `docs/PHASE_1.md` (new)
- `docs/PHASE_2.md` (new)
- `docs/PHASE_3.md` (new)
- `docs/PHASE_4.md` (new)
- `docs/PHASE_5.md` (new)
- `docs/PHASE_6.md` (new)
- `CHANGELOG.md` (new)

**How it was verified:**
- All docs reviewed for completeness and cross-references
- Devin Machine smoke test: `gh auth status`, `pip-audit --version`, `semgrep --version`, `docker --version` all pass
- Playbook created and visible in Devin UI (ID: `playbook-77e36f049a66446c821245596544412a`)

**What the next phase needs to know:**
- GitHub Projects v2 webhooks ARE supported — `projects_v2_item.edited` fires on status field changes. Primary trigger confirmed feasible.
- Devin API v3 supports: session creation with playbook attachment, polling, messaging, attachments, scheduled sessions
- Tech stack locked: FastAPI + SQLite + Docker Compose + htmx dashboard
- Both repos cloned and authenticated on the Devin Machine
- All phase prompts reference the `cognition-takehome-prompting-playbook` Devin Playbook

**Open questions / known gaps:**
- Devin API key (`DEVIN_API_KEY`) and org ID (`DEVIN_ORG_ID`) must be provisioned as secrets before Phase 2 can test session creation
- GitHub webhook secret needs to be generated and configured on the fork before Phase 2 can receive webhooks
- The exact GitHub Projects v2 field node IDs for the Status field on the fork's project board will only be known after Phase 1 creates the board
- localhost.run SSH tunnel (zero-signup) for local webhook testing during Phase 2: `ssh -R 80:localhost:8000 nokey@localhost.run`

---

## [PHASE_2] — 2026-04-12 — Orchestrator backend with webhook receiver and Devin API client

**What changed:**
- Built FastAPI orchestrator in `orchestrator/` directory
- Implemented webhook receiver (`POST /webhooks/github`) with HMAC-SHA256 verification
- Implemented Devin API v3 client (session creation, polling, messaging)
- Implemented GitHub API client (issue resolution via GraphQL, comments, labels)
- Implemented state machine with SQLite persistence (backlog → planning → building → reviewing → done)
- Created prompt templates for planner/builder/reviewer Devin sessions
- Created Docker Compose configuration for single-command startup
- Added health check (`GET /health`) and metrics stub (`GET /api/metrics`)
- Added dashboard stub (`GET /dashboard`) — full implementation in Phase 4
- Added scanner stub (`scanner.py`) — full implementation in Phase 3
- Added 53 unit tests covering webhook, state machine, Devin client, prompts, and DB layer
- Updated `.gitignore` for Python/Docker artifacts

**Files touched:**
- `orchestrator/` (new directory, all files)
  - `orchestrator/pyproject.toml` (new)
  - `orchestrator/Dockerfile` (new)
  - `orchestrator/app/__init__.py` (new)
  - `orchestrator/app/main.py` (new)
  - `orchestrator/app/config.py` (new)
  - `orchestrator/app/webhook.py` (new)
  - `orchestrator/app/devin_client.py` (new)
  - `orchestrator/app/github_client.py` (new)
  - `orchestrator/app/state_machine.py` (new)
  - `orchestrator/app/prompts.py` (new)
  - `orchestrator/app/scanner.py` (new)
  - `orchestrator/app/db.py` (new)
  - `orchestrator/app/dashboard.py` (new)
  - `orchestrator/templates/dashboard.html` (new)
  - `orchestrator/tests/` (new, 6 test files)
- `docker-compose.yml` (new)
- `.gitignore` (new)
- `CHANGELOG.md` (appended this entry)

**How it was verified:**
- All 53 unit tests pass: `python -m pytest orchestrator/tests/ -v`
- Webhook rejects invalid HMAC signatures (returns 401)
- Webhook accepts valid payloads and routes by event type
- State machine validates transitions (rejects skips, allows error from any state)
- Devin client correctly creates sessions, polls status, handles timeouts
- Prompt templates render with all expected fields
- DB layer handles upsert, session logging, and aggregate metrics

**What the next phase needs to know:**
- Orchestrator runs on port 8000 via `docker compose up --build`
- Webhook endpoint: `POST /webhooks/github` (expects `projects_v2_item` events)
- Dashboard endpoint: `GET /dashboard` (stub — full htmx dashboard in Phase 4)
- Metrics API: `GET /api/metrics` (returns JSON with issue counts, session counts, activity feed)
- Health check: `GET /health` (returns `{"status": "ok"}`)
- Database file: `data/orchestrator.db` (mounted via Docker volume)
- Environment variables required: `DEVIN_API_KEY`, `DEVIN_ORG_ID`, `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`
- State machine supports transitions: backlog → planning → building → reviewing → done (plus error from any state)
- Devin sessions are created with tags `[issue-{N}, {role}]` for filtering

**Open questions / known gaps:**
- Docker Compose build not yet tested end-to-end (will verify before PR merge)
- Real Devin API session creation not tested (mocked in unit tests) — requires API key in environment
- Webhook payload parsing assumes `changes.field_value.to.name` contains the new status column name — needs validation against real GitHub Projects v2 payloads once Phase 1 creates the board
- Scanner module is a stub — full implementation deferred to Phase 3
