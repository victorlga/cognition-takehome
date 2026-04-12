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

Organize metrics into four groups that answer what a VP of Engineering cares about.
See `docs/ARCHITECTURE.md` "Observability" section for the full rationale.

**Pipeline Health ("Is the system working right now?")**

| Metric | Query Logic | Visualization |
|--------|------------|---------------|
| **Active Devin Sessions** | COUNT from `session_log` WHERE status = 'running', GROUP BY session_type | Big number card with type breakdown |
| **Issues by Status** | GROUP BY status from `issue_state` | Horizontal bar chart (pipeline funnel) |
| **Error Rate** | COUNT(error) / COUNT(total) from `session_log` + latest error messages | Percentage card, red if > 0 |

**Velocity & Efficiency ("Is this worth the investment?")**

| Metric | Query Logic | Visualization |
|--------|------------|---------------|
| **Time-to-Remediation (TTR)** | Median and p90 of (done_at - planning_started_at) from `issue_state` WHERE status = 'done'. Also compute per-stage breakdown (planning, building, reviewing). | Big number (median hours) + stacked bar per issue |
| **Throughput** | COUNT from `issue_state` WHERE status = 'done' grouped by date | Line chart with trend |
| **Session Success Rate** | COUNT(completed) / COUNT(total) from `session_log` | Percentage + donut chart |
| **Devin Compute Cost per Fix** | SUM(duration_seconds) / COUNT(DISTINCT issue_id) from `session_log` WHERE status = 'completed' | Big number (minutes per fix) |

**Risk Posture ("Are we safer than yesterday?")**

| Metric | Query Logic | Visualization |
|--------|------------|---------------|
| **Open vs. Closed Trend** | Cumulative COUNT of issues created vs. issues done, by date | Dual line chart (gap should shrink) |
| **Severity Breakdown** | GROUP BY category from `issue_state` | Donut chart (security / bug / dependency / SAST) |
| **Mean Time to First Response** | AVG(first_session_started_at - created_at) from `issue_state` | Big number (minutes) |

**Recent Activity ("What just happened?")**

| Metric | Query Logic | Visualization |
|--------|------------|---------------|
| **Activity Feed** | Latest 20 entries from `session_log` ORDER BY started_at DESC, joined with issue_state for titles/PR links | Scrollable table with status badges |

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
- **Summary Cards Row** (4 cards): Median TTR, Throughput (this week), Session Success Rate, Active Sessions
- **Pipeline Funnel Row**: Issues by Status (horizontal bar) + Error Rate indicator
- **Trends Row**: Open vs. Closed Vulnerability Trend (dual line) + Throughput over Time (line with trend)
- **Breakdown Row**: Severity/Category donut + TTR by stage stacked bar + Cost per Fix
- **Activity Feed**: Recent session activity table with status badges, links to PRs/issues
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
- All 4 metric groups displayed: Pipeline Health, Velocity & Efficiency, Risk Posture, Activity Feed
- Auto-refresh works
- JSON API at `/api/metrics` returns structured data covering all metric groups
- Dashboard looks polished enough to show a VP of Engineering in a Loom
- Screenshot captured for Loom prep

---

## CHANGELOG Entry Template

```markdown
## [PHASE_4] — YYYY-MM-DD — Observability dashboard with metrics and activity feed

**What changed:**
- Implemented full dashboard at /dashboard with 4 metric groups
- Pipeline Health: active sessions, issues by status funnel, error rate
- Velocity: TTR (median + p90 + per-stage), throughput trend, success rate, cost per fix
- Risk Posture: open vs. closed trend, severity breakdown, MTFR
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
