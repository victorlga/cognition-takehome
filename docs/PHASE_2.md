# Phase 2 — Orchestrator Backend

> **Before starting, load the Devin Playbook `cognition-takehome-prompting-playbook` and follow it throughout this session.**

**Depends on:** PHASE_0 complete (verify via CHANGELOG.md entry "Bootstrap planning docs, playbook, machine, and wikis")

**Can run in parallel with:** Phase 1 (no shared mutable state)

---

## Goal

Build the FastAPI orchestrator that receives GitHub webhooks, manages issue state, and spawns Devin sessions (planner / builder / reviewer) via the Devin API v3.

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
- **GitHub Projects v2 webhooks** (`projects_v2_item.edited`) as primary trigger
- **Issue labels** (`state:planning`, `state:building`, etc.) as fallback trigger
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
│   ├── webhook.py
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
    github_webhook_secret: str  # GITHUB_WEBHOOK_SECRET
    github_repo: str = "victorlga/superset"
    database_url: str = "sqlite+aiosqlite:///./data/orchestrator.db"
    devin_api_base: str = "https://api.devin.ai/v3"
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
- Resolving project item `content_node_id` to issue details (GraphQL)
- Reading issue body and comments
- Posting issue comments (planner output)
- Reading the Status field value from webhook payload
- Creating labels on the fork if missing

### Step 6: Implement `prompts.py`

Template-based prompt builder using the templates from `ARCHITECTURE.md`:
- `build_planner_prompt(issue) -> str`
- `build_builder_prompt(issue, plan) -> str`
- `build_reviewer_prompt(issue, pr_url) -> str`

### Step 7: Implement `state_machine.py`

State transition logic:
- `handle_status_change(item_id, old_status, new_status)` — the main entry point
- Maps status transitions to Devin session creation
- Validates transitions (no skipping states)
- Updates `issue_state` table
- Spawns appropriate Devin session via `devin_client`

### Step 8: Implement `webhook.py`

FastAPI router for the webhook endpoint:

```python
@router.post("/webhooks/github")
async def github_webhook(request: Request):
    # 1. Verify HMAC-SHA256 signature
    # 2. Parse event type from X-GitHub-Event header
    # 3. Handle projects_v2_item.edited events
    # 4. Extract status field change from payload
    # 5. Delegate to state_machine.handle_status_change()
    # 6. Return 200 OK
```

### Step 9: Implement `main.py`

FastAPI application setup:
- Include webhook router
- Include dashboard router
- Initialize database on startup
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
      - GITHUB_WEBHOOK_SECRET=${GITHUB_WEBHOOK_SECRET}
    volumes:
      - ./data:/app/data
```

### Step 14: Test Locally

```bash
# Build and start
docker compose up --build -d

# Health check
curl http://localhost:8000/health

# Test webhook with a mock payload
curl -X POST http://localhost:8000/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: projects_v2_item" \
  -H "X-Hub-Signature-256: sha256=<computed>" \
  -d '{"action": "edited", "changes": {"field_value": {"field_node_id": "test"}}, "projects_v2_item": {"id": 1, "content_node_id": "I_test", "content_type": "Issue"}}'

# Check metrics stub
curl http://localhost:8000/api/metrics
```

### Step 15: Write Unit Tests

Create `orchestrator/tests/` with:
- `test_webhook.py` — HMAC verification, payload parsing, event routing
- `test_state_machine.py` — state transitions, invalid transition rejection
- `test_devin_client.py` — session creation (mocked), polling logic
- `test_prompts.py` — prompt template rendering

Run with: `python -m pytest orchestrator/tests/ -v`

---

## Deliverables

- [ ] `orchestrator/` directory with all source files
- [ ] `Dockerfile` that builds cleanly
- [ ] `docker-compose.yml` at repo root
- [ ] Webhook endpoint that verifies HMAC and parses `projects_v2_item` events
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
3. Webhook endpoint rejects requests with invalid HMAC signatures (returns 401)
4. Webhook endpoint accepts valid payloads and logs state transitions
5. Unit tests pass: `python -m pytest orchestrator/tests/ -v`
6. `curl http://localhost:8000/api/metrics` returns valid JSON

---

## Definition of Done

- `docker compose up` starts the orchestrator successfully
- Webhook endpoint accepts and verifies GitHub payloads
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
- Implemented webhook receiver with HMAC verification
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
- Webhook accepts valid payloads, rejects invalid signatures
- Unit tests pass with >80% coverage
- Metrics endpoint returns valid JSON

**What the next phase needs to know:**
- Orchestrator runs on port 8000
- Webhook endpoint: POST /webhooks/github
- Dashboard endpoint: GET /dashboard (stub, full in Phase 4)
- Metrics API: GET /api/metrics
- Database file: data/orchestrator.db

**Open questions / known gaps:**
- [list any issues]
```
