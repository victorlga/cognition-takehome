# Phase 4 — Observability Dashboard

> **Before starting, load the Devin Playbook `cognition-takehome-prompting-playbook` and follow it throughout this session.**

**Depends on:** PHASE_2 complete (verify via CHANGELOG.md entry "Orchestrator backend")

---

## Goal

Build the lightweight observability dashboard that answers the VP-of-Engineering question: **"How would an engineering leader know this is working?"**

---

## Inputs to Read

1. `CHANGELOG.md` — read the entire file
2. `docs/TAKEHOME.md` — the full assignment spec
3. `docs/PLAN.md` — master plan
4. `docs/ARCHITECTURE.md` — dashboard design, metrics list, tech stack

---

## Architecture / Business Decisions Already Made

- Dashboard served at `/dashboard` by the same FastAPI process
- Rendered via **Jinja2 templates + htmx** for auto-refresh
- **Chart.js** for visualizations (loaded via CDN)
- Metrics computed from SQLite on each page load (demo-scale)
- JSON API at `/api/metrics` for programmatic access
- No separate frontend build step — single-page, server-rendered

---

## Tech Stack

- Jinja2 (templates)
- htmx (auto-refresh, partial updates)
- Chart.js (bar charts, line charts)
- FastAPI (serving)
- SQLite (data source)

---

## Procedure

### Step 1: Define Metrics

Implement these metrics (queries against the SQLite database):

| Metric | Query Logic | Visualization |
|--------|------------|---------------|
| **Active Devin Sessions** | COUNT from `session_log` WHERE status = 'running' | Big number card |
| **Issues by Status** | GROUP BY status from `issue_state` | Horizontal bar chart |
| **Time-to-Remediation** | AVG(done_at - created_at) from `issue_state` WHERE status = 'done' | Big number (hours) |
| **Session Success Rate** | COUNT(completed) / COUNT(total) from `session_log` | Percentage + donut chart |
| **Throughput** | COUNT from `issue_state` WHERE status = 'done' grouped by date | Line chart |
| **Recent Activity** | Latest 20 entries from `session_log` ORDER BY started_at DESC | Activity feed table |

### Step 2: Implement `/api/metrics`

Update the stub from Phase 2 to return real data:

```json
{
  "active_sessions": 2,
  "issues": {
    "backlog": 1,
    "planning": 0,
    "building": 1,
    "reviewing": 1,
    "done": 2,
    "error": 0
  },
  "median_time_to_remediation_hours": 1.5,
  "session_success_rate": 0.85,
  "total_sessions": 12,
  "completed_sessions": 10,
  "failed_sessions": 2,
  "recent_activity": [
    {
      "session_id": "devin-abc123",
      "session_type": "builder",
      "issue_id": 42,
      "status": "completed",
      "started_at": "2026-04-12T10:00:00Z",
      "duration_seconds": 3600
    }
  ]
}
```

### Step 3: Build the Dashboard Template

Create `orchestrator/templates/dashboard.html`:

- **Header**: "Vulnerability Remediation System — Dashboard"
- **Summary Cards Row**: Active Sessions, Issues Remediated, Success Rate, Median TTR
- **Charts Row**: Issues by Status (bar), Throughput over Time (line)
- **Activity Feed**: Recent session activity table with status badges
- **Auto-refresh**: htmx polls `/api/metrics` every 30 seconds and updates the page

Design notes:
- Clean, professional look (light theme, consistent spacing)
- Color-coded status badges (green = done, blue = building, yellow = planning, red = error)
- Responsive layout (CSS grid)
- No JavaScript framework — vanilla JS + Chart.js + htmx only

### Step 4: Implement `dashboard.py`

Update the dashboard routes:

```python
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    metrics = await compute_metrics()
    return templates.TemplateResponse("dashboard.html", {"request": request, "metrics": metrics})

@router.get("/api/metrics")
async def api_metrics():
    return await compute_metrics()
```

### Step 5: Test with Sample Data

Insert sample data into SQLite to verify the dashboard renders correctly:

```python
# Test script to seed sample data
import aiosqlite
import asyncio

async def seed():
    async with aiosqlite.connect("data/orchestrator.db") as db:
        # Insert sample issue states
        # Insert sample session logs
        await db.commit()

asyncio.run(seed())
```

### Step 6: Verify

1. `curl http://localhost:8000/api/metrics` returns valid JSON with all fields
2. Open `http://localhost:8000/dashboard` in a browser — charts render, cards show data
3. Wait 30 seconds — data auto-refreshes via htmx
4. Take a screenshot for the Loom video prep

---

## Deliverables

- [ ] `orchestrator/app/dashboard.py` — full dashboard routes with real metrics
- [ ] `orchestrator/templates/dashboard.html` — complete Jinja2 + htmx + Chart.js template
- [ ] `/api/metrics` endpoint returning all metrics as JSON
- [ ] `/dashboard` page rendering with charts and activity feed
- [ ] Auto-refresh working via htmx
- [ ] Screenshot of the dashboard with sample data

---

## Test Plan & Verification

1. `curl http://localhost:8000/api/metrics` returns valid JSON
2. Dashboard page loads without errors in browser console
3. Charts render with correct data
4. Activity feed shows recent sessions
5. Auto-refresh updates the page every 30 seconds
6. Dashboard looks professional enough for a VP audience

---

## Definition of Done

- Dashboard renders at `/dashboard` with real or sample data
- All 6 metrics are displayed
- Auto-refresh works
- JSON API at `/api/metrics` returns structured data
- Screenshot captured for Loom prep

---

## CHANGELOG Entry Template

```markdown
## [PHASE_4] — YYYY-MM-DD — Observability dashboard with metrics and activity feed

**What changed:**
- Implemented full dashboard at /dashboard with 6 metrics
- Charts: issues by status (bar), throughput (line), success rate (donut)
- Activity feed with recent Devin sessions
- Auto-refresh via htmx (30s polling)
- JSON API at /api/metrics

**Files touched:**
- `orchestrator/app/dashboard.py` (updated)
- `orchestrator/templates/dashboard.html` (new)
- `CHANGELOG.md` (appended this entry)

**How it was verified:**
- Dashboard renders with sample data
- API returns valid JSON
- Auto-refresh confirmed in browser
- Screenshot captured

**What the next phase needs to know:**
- Dashboard URL: http://localhost:8000/dashboard
- Metrics API: http://localhost:8000/api/metrics
- Dashboard screenshot available for Loom

**Open questions / known gaps:**
- [list any issues]
```
