"""Dashboard routes and metrics API.

The full htmx dashboard is Phase 4. For now this provides:
- GET /dashboard        — stub page
- GET /api/metrics      — JSON metrics from the database
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from app.db import get_metrics

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page() -> HTMLResponse:
    """Stub dashboard — full implementation in Phase 4."""
    html = """<!DOCTYPE html>
<html>
<head><title>Orchestrator Dashboard</title></head>
<body>
  <h1>Vulnerability Remediation Dashboard</h1>
  <p>Full dashboard coming in Phase 4. <a href="/api/metrics">View raw metrics JSON</a>.</p>
  <p><a href="/health">Health check</a></p>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/api/metrics")
async def metrics_api() -> JSONResponse:
    """Return aggregate metrics as JSON."""
    data = await get_metrics()
    return JSONResponse(content=data)
