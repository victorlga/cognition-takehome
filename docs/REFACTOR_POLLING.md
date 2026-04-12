# Refactor Plan: Webhook → Polling-based Architecture

## Problem
The current system requires GitHub webhooks to push events to the orchestrator, which means the server must be publicly reachable. A recruiter running `docker compose up` locally can't receive webhooks without a tunnel or deployment.

## Solution
Replace the **webhook-driven** primary trigger with a **polling-based** trigger. The orchestrator periodically polls the GitHub API for `state:*` label changes on issues, eliminating the need for inbound connectivity. The webhook endpoint is preserved as an optional secondary trigger.

---

## Changes by File (Control/Data Flow Order)

### 1. `orchestrator/app/config.py` — Add polling configuration

```python
class Settings(BaseSettings):
    # ... existing fields ...
    poll_interval_seconds: int = 30        # NEW: interval between poll cycles
    polling_enabled: bool = True           # NEW: enable/disable polling (disable for webhook-only mode)
```

### 2. `orchestrator/app/github_client.py` — Add issue listing method

```python
class GitHubClient:
    # ... existing methods ...

    async def list_issues_with_labels(self, labels: list[str], state: str = "open") -> list[dict[str, Any]]:
        """GET /repos/{repo}/issues?labels={labels}&state={state}
        
        Fetches all open issues matching the given labels.
        Used by the poller to discover issues with state:* labels.
        """
```

### 3. NEW `orchestrator/app/poller.py` — Core polling logic

```python
"""Polling-based state machine driver.

Replaces inbound webhooks as the primary trigger. Polls the GitHub API
for issues with ``state:*`` labels and triggers state transitions when
a label-based state differs from the DB state.
"""

STATE_LABELS: list[str] = ["state:planning", "state:building", "state:reviewing", "state:done"]

def _extract_state_from_labels(labels: list[dict[str, Any]]) -> str | None:
    """Extract the pipeline state from an issue's label list.
    
    Returns the state string (e.g. "planning") if a state:* label is found, else None.
    Handles multiple state:* labels by taking the most advanced one.
    """

async def poll_once(github: GitHubClient | None = None, devin: DevinClient | None = None) -> list[dict[str, Any]]:
    """Execute a single poll cycle.
    
    1. Fetch all open issues on the repo with any state:* label
    2. For each issue, extract the state:* label
    3. Compare against the DB state
    4. If different and the transition is valid, call handle_status_change()
    
    Returns a list of actions taken (for logging/testing).
    """

async def start_polling_loop() -> None:
    """Infinite loop that calls poll_once() every N seconds.
    
    Reads interval from settings.poll_interval_seconds.
    Catches and logs exceptions per cycle (never crashes the loop).
    """
```

**Data flow:**
```
GitHub API (outbound GET) → poll_once() → compare with DB → handle_status_change() → DevinClient.create_session()
```

### 4. `orchestrator/app/main.py` — Start poller on startup

```python
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialise the database and start the background poller."""
    await init_db()
    poll_task: asyncio.Task | None = None
    if settings.polling_enabled:            # NEW: start poller
        poll_task = asyncio.create_task(start_polling_loop())
    yield
    if poll_task and not poll_task.done():   # NEW: clean shutdown
        poll_task.cancel()
```

### 5. `orchestrator/app/webhook.py` — No functional changes

Preserved as-is. Still works as a secondary/optional trigger. The webhook and poller can coexist safely because `handle_status_change()` already validates transitions against the DB state — a duplicate trigger is a no-op (invalid transition "planning→planning" is rejected).

### 6. `orchestrator/app/state_machine.py` — No changes

Already receives issue data directly (not from webhook payloads). Both the webhook handler and the poller call the same `handle_status_change()` function.

### 7. `orchestrator/app/db.py` — No changes

Existing `get_issue()`, `upsert_issue()`, `list_issues()` are sufficient.

### 8. NEW `orchestrator/tests/test_poller.py` — Tests for the poller

```python
class TestExtractStateFromLabels:
    # Test extraction from label lists, multiple state labels, no state labels, etc.

class TestPollOnce:
    # Mock GitHubClient.list_issues_with_labels() to return issues with various label states
    # Mock DB state to simulate new vs. already-processed transitions
    # Verify handle_status_change() is called for new transitions
    # Verify no-op for already-processed issues
    # Verify error handling when GitHub API fails
```

### 9. `orchestrator/app/__init__.py` — No changes

### 10. Documentation updates

- `docs/ARCHITECTURE.md`: Update primary trigger section, Mermaid diagram, add polling details
- `CHANGELOG.md`: Append new entry for this refactor

### 11. `docker-compose.yml` — Add optional polling config

```yaml
services:
  orchestrator:
    # ... existing ...
    environment:
      # ... existing ...
      - POLL_INTERVAL_SECONDS=${POLL_INTERVAL_SECONDS:-30}   # NEW
```

---

## Idempotency & Deduplication

The system is naturally idempotent because:
1. `handle_status_change()` checks DB state before acting
2. If `old_status == new_status`, the transition is invalid and rejected
3. The poller only triggers when the label-based state **differs** from the DB state
4. The webhook and poller can coexist — duplicate triggers are harmless no-ops

## Files NOT Changed

| File | Why |
|------|-----|
| `state_machine.py` | Already accepts data directly — both triggers use the same entry point |
| `devin_client.py` | No changes needed — session creation API is unchanged |
| `prompts.py` | Template logic is trigger-agnostic |
| `scanner.py` | Stub — unrelated to trigger mechanism |
| `dashboard.py` | Reads from DB — trigger-agnostic |
| `db.py` | Existing queries are sufficient |

## Summary of New/Modified Symbols

| Symbol | File | Change |
|--------|------|--------|
| `Settings.poll_interval_seconds` | `config.py` | NEW field |
| `Settings.polling_enabled` | `config.py` | NEW field |
| `GitHubClient.list_issues_with_labels()` | `github_client.py` | NEW method |
| `_extract_state_from_labels()` | `poller.py` | NEW function |
| `poll_once()` | `poller.py` | NEW function |
| `start_polling_loop()` | `poller.py` | NEW function |
| `lifespan()` | `main.py` | MODIFIED — starts poller task |
| `docker-compose.yml` | root | MODIFIED — add POLL_INTERVAL_SECONDS env |
