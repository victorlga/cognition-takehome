# Phase 2 — Orchestrator Backend

> **Before starting, load the Devin Playbook `cognition-takehome-prompting-playbook` and follow it throughout this session.**

**Depends on:** PHASE_0 complete (verify via CHANGELOG.md entry "Bootstrap planning docs, playbook, machine, and wikis")

**Can run in parallel with:** Phase 1 (no shared mutable state)

---

## Goal

Build the FastAPI orchestrator that **polls for issue label changes**, manages issue state, and spawns Devin sessions (planner / builder / reviewer) via the Devin API v3.

---

## Inputs to Read

1. `CHANGELOG.md` — read the entire file to understand prior work
2. `docs/TAKEHOME.md` — the full assignment spec
3. `docs/PLAN.md` — master plan and phase overview
4. `docs/ARCHITECTURE.md` — system architecture, tech stack, DB schema, prompt templates, directory structure

---

## Architecture / Business Decisions Already Made

- **FastAPI** (Python 3.12) with `httpx` for async HTTP
- **SQLite** via `aiosqlite` for persistence
- **Docker Compose** for deployment
- **Polling** for `state:*` labels as the **primary trigger** — a background `asyncio` task polls the GitHub API every N seconds. This eliminates the need for a publicly-reachable URL, so `docker compose up` just works.
- The GitHub Projects v2 board is still used for visual kanban tracking but does not drive the state machine
- Prompt templates for planner/builder/reviewer defined in `ARCHITECTURE.md`
- DB schema defined in `ARCHITECTURE.md`
- Directory structure defined in `ARCHITECTURE.md`

---

## Tech Stack

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12 | Runtime |
| FastAPI | latest | Web framework |
| httpx | latest | Async HTTP client (Devin API, GitHub API) |
| aiosqlite | latest | Async SQLite |
| uvicorn | latest | ASGI server |
| Jinja2 | latest | Dashboard templates |
| pydantic | v2 | Request/response validation |
| Docker | latest | Containerization |

---

## Procedure

### Step 1: Scaffold the Project

Create the directory structure from `ARCHITECTURE.md`:

```
orchestrator/
├── Dockerfile
├── pyproject.toml
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── poller.py
│   ├── devin_client.py
│   ├── github_client.py
│   ├── state_machine.py
│   ├── prompts.py
│   ├── scanner.py
│   ├── db.py
│   └── dashboard.py
└── templates/
    └── dashboard.html
```

Use `pyproject.toml` with dependencies:
```toml
[project]
name = "vuln-remediation-orchestrator"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",
    "aiosqlite>=0.20",
    "jinja2>=3.1",
    "pydantic>=2.0",
    "python-multipart>=0.0.9",
]
```

### Step 2: Implement `config.py`

Load all settings from environment variables using Pydantic `BaseSettings`:

```python
class Settings(BaseSettings):
    devin_api_key: str          # DEVIN_API_KEY
    devin_org_id: str           # DEVIN_ORG_ID
    github_token: str           # GITHUB_TOKEN
    github_repo: str = "victorlga/superset"
    database_url: str = "sqlite+aiosqlite:///./data/orchestrator.db"
    devin_api_base: str = "https://api.devin.ai/v3"
    poll_interval_seconds: int = 30
    polling_enabled: bool = True
```

### Step 3: Implement `db.py`

Create the SQLite tables from the schema in `ARCHITECTURE.md`:
- `issue_state` table
- `session_log` table
- Async init, query, and update functions

### Step 4: Implement `devin_client.py`

Wrap the Devin API v3 endpoints:

```python
class DevinClient:
    async def create_session(self, prompt: str, playbook_id: str = None) -> dict:
        """POST /v3/organizations/{org_id}/sessions"""

    async def get_session(self, session_id: str) -> dict:
        """GET /v3/organizations/{org_id}/sessions/{session_id}"""

    async def send_message(self, session_id: str, message: str) -> dict:
        """POST /v3/organizations/{org_id}/sessions/{session_id}/messages"""

    async def get_messages(self, session_id: str) -> list:
        """GET /v3/organizations/{org_id}/sessions/{session_id}/messages"""

    async def poll_until_complete(self, session_id: str, timeout: int = 7200) -> str:
        """Poll session status until terminal state"""
```

### Step 5: Implement `github_client.py`

Wrap the GitHub API for:
- Listing issues with specific labels (for the poller)
- Reading issue body and comments
- Posting issue comments (planner output)
- Managing `state:*` labels on issues
- Creating labels on the fork if missing

### Step 6: Implement `prompts.py`

Template-based prompt builder using the templates from `ARCHITECTURE.md`:
- `build_planner_prompt(issue) -> str`
- `build_builder_prompt(issue, plan) -> str`
- `build_reviewer_prompt(issue, pr_url) -> str`

### Step 7: Implement `state_machine.py`

State transition logic:
- `handle_status_change(issue_number, new_status, issue_title, ...)` — the main entry point
- Maps status transitions to Devin session creation
- Validates transitions (no skipping states)
- Updates `issue_state` table
- Spawns appropriate Devin session via `devin_client`

### Step 8: Implement `poller.py` (Primary Trigger)

Polling-based state machine driver:

```python
async def extract_state_from_labels(labels: list[dict]) -> str | None:
    """Derive pipeline state from an issue's label list."""

async def poll_once(github=None, devin=None) -> list[dict]:
    """Single poll cycle: fetch issues, compare DB state, fire transitions."""

async def start_polling_loop() -> None:
    """Infinite loop calling poll_once every N seconds."""
```

### Step 9: Implement `main.py`

FastAPI application setup:
- Include dashboard router
- Initialize database on startup
- **Start background poller on startup** (if `POLLING_ENABLED=true`)
- Cancel poller on shutdown
- Health check at `GET /health`
- CORS middleware (for dashboard)

### Step 10: Implement `dashboard.py` (stub)

Minimal routes — the full dashboard is Phase 4. For now:
- `GET /dashboard` — returns "Dashboard coming in Phase 4"
- `GET /api/metrics` — returns basic counts from the database

### Step 11: Implement `scanner.py` (stub)

Placeholder for the periodic vulnerability scanner. Full implementation is a Phase 3 enhancement.

### Step 12: Create Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install .
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Step 13: Create `docker-compose.yml`

```yaml
services:
  orchestrator:
    build: ./orchestrator
    ports:
      - "8000:8000"
    environment:
      - DEVIN_API_KEY=${DEVIN_API_KEY}
      - DEVIN_ORG_ID=${DEVIN_ORG_ID}
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - POLL_INTERVAL_SECONDS=${POLL_INTERVAL_SECONDS:-30}
      - POLLING_ENABLED=${POLLING_ENABLED:-true}
    volumes:
      - ./data:/app/data
```

### Step 14: Test Locally

```bash
# Build and start
docker compose up --build -d

# Health check
curl http://localhost:8000/health

# The poller starts automatically — check logs for "Poller started"
docker compose logs -f orchestrator

# Check metrics stub
curl http://localhost:8000/api/metrics
```

### Step 15: Write Unit Tests

Create `orchestrator/tests/` with:
- `test_poller.py` — polling logic, label extraction, transition detection
- `test_state_machine.py` — state transitions, invalid transition rejection
- `test_devin_client.py` — session creation (mocked), polling logic
- `test_prompts.py` — prompt template rendering

Run with: `python -m pytest orchestrator/tests/ -v`

---

## Deliverables

- [ ] `orchestrator/` directory with all source files
- [ ] `Dockerfile` that builds cleanly
- [ ] `docker-compose.yml` at repo root
- [ ] Polling-based trigger that detects `state:*` label changes on issues
- [ ] Devin API client that can create sessions, poll status, send messages
- [ ] State machine with SQLite persistence
- [ ] Prompt templates for planner/builder/reviewer
- [ ] Health check and metrics stub endpoints
- [ ] Unit tests with >80% coverage on core logic
- [ ] `.gitignore` updated for Python/Docker artifacts

---

## Test Plan & Verification

1. `docker compose up --build` starts without errors
2. `curl http://localhost:8000/health` returns `{"status": "ok"}`
3. Poller starts automatically and logs "Poller started — polling every 30 seconds"
4. Unit tests pass: `python -m pytest orchestrator/tests/ -v`
5. `curl http://localhost:8000/api/metrics` returns valid JSON

---

## Definition of Done

- `docker compose up` starts the orchestrator with polling enabled (zero webhook setup needed)
- Poller detects label changes and triggers state transitions
- Devin sessions can be created via the API client (verified with a real test call if API key is available, otherwise mocked)
- State transitions logged to SQLite
- All unit tests pass
- PR opened against `cognition-takehome/main`

---

## CHANGELOG Entry Template

```markdown
## [PHASE_2] — YYYY-MM-DD — Orchestrator backend with webhook receiver and Devin API client

**What changed:**
- Built FastAPI orchestrator in `orchestrator/` directory
- Implemented polling-based trigger for `state:*` label detection
- Implemented Devin API v3 client (sessions, polling, messaging)
- Implemented state machine with SQLite persistence
- Created Docker Compose configuration
- Added unit tests

**Files touched:**
- `orchestrator/` (new directory, all files)
- `docker-compose.yml` (new)
- `.gitignore` (updated)
- `CHANGELOG.md` (appended this entry)

**How it was verified:**
- Docker Compose builds and starts cleanly
- Health check returns 200
- Poller detects label changes and triggers transitions
- Unit tests pass with >80% coverage
- Metrics endpoint returns valid JSON

**What the next phase needs to know:**
- Orchestrator runs on port 8000
- Poller runs as background task (primary trigger, interval configurable via POLL_INTERVAL_SECONDS)
- Dashboard endpoint: GET /dashboard (stub, full in Phase 4)
- Metrics API: GET /api/metrics
- Database file: data/orchestrator.db

**Open questions / known gaps:**
- [list any issues]
```
