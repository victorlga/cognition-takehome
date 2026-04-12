# Testing the Orchestrator Dashboard

## Overview
The orchestrator serves a Jinja2 + htmx + Chart.js observability dashboard at `/dashboard` and a JSON API at `/api/metrics`. Both endpoints compute metrics from SQLite on each page load.

## Devin Secrets Needed
None — the dashboard and API do not require authentication for local testing.

## Prerequisites
- Python dependencies installed: `cd orchestrator && pip install -e ".[dev]"`
- Playwright browsers installed (for headless screenshot verification): `playwright install chromium`

## Setup

### 1. Seed Sample Data
```bash
cd orchestrator && python -m scripts.seed_sample_data
```
This populates `data/orchestrator.db` with 5 sample issues and 11 session logs.

### 2. Start the Server
```bash
cd orchestrator && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Verify Health
```bash
curl http://localhost:8000/health
# Expected: {"status":"ok"}
```

## Testing the Dashboard

### JSON API Verification
```bash
curl -s http://localhost:8000/api/metrics | python3 -m json.tool | head -20
```
Expected keys: `active_sessions`, `issues`, `median_time_to_remediation_hours`, `session_success_rate`, `total_sessions`, `completed_sessions`, `failed_sessions`, `error_rate`, `recent_errors`, `throughput_by_day`, `open_trend`, `closed_trend`, `severity_breakdown`, `ttr_per_issue`, `cost_per_fix_minutes`, `mean_time_to_first_response_minutes`, `recent_activity`.

### Browser Dashboard Verification
Open `http://localhost:8000/dashboard` in a browser. Verify:
1. **Summary cards** (4 cards): Median TTR, Issues Remediated, Session Success Rate, Active Sessions
2. **Pipeline Health**: Horizontal bar chart (issues by status) + Error Rate card
3. **Velocity & Efficiency**: Open vs Closed trend (dual line chart) + Throughput over Time (line chart)
4. **Risk Posture**: Severity donut chart + TTR by Stage stacked bar + Efficiency metrics
5. **Activity Feed**: Table with 11+ session rows, color-coded status badges, PR links

### Auto-Refresh Verification
The dashboard uses htmx to poll `/api/metrics` every 30 seconds. To verify:
1. Note the "Last updated" timestamp in the header
2. Wait 30+ seconds
3. The timestamp should update automatically
4. A blue progress bar should briefly animate at the top of the page

**Note:** htmx auto-refresh updates summary cards and charts but does NOT re-render the activity feed table or error details section. Those require a full page reload.

### Headless Screenshot (Playwright)
For CI or headless environments without a display:
```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto("http://localhost:8000/dashboard", wait_until="networkidle")
    page.wait_for_timeout(3000)
    page.screenshot(path="dashboard_screenshot.png", full_page=True)
    browser.close()
```

## Known Gotchas

- **Starlette 1.0 TemplateResponse API**: Uses `TemplateResponse(request, name, context={...})` — the pre-1.0 signature `TemplateResponse(name, {"request": request, ...})` causes `TypeError: unhashable type: 'dict'`.
- **Chrome on Devin VM**: The system Chrome binary is at `/opt/.devin/chrome/chrome/linux-*/chrome-linux64/chrome`. The `google-chrome` wrapper uses CDP on port 29229. Start Chrome with `--remote-debugging-port=29229 --display=:0` to get it visible on the desktop.
- **Chart.js and htmx via CDN**: Both are loaded from `cdn.jsdelivr.net` and `unpkg.com`. If either CDN is unreachable, the dashboard will render without charts or auto-refresh.
- **Database path**: The SQLite database is at `orchestrator/data/orchestrator.db` (created automatically by `init_db()` on server startup).

## Unit Tests
```bash
cd orchestrator && python -m pytest tests/ -v
```
Expect 62 tests to pass. The `TestMetrics` class covers the `get_metrics()` function with empty and populated databases.
