"""Dashboard routes and metrics API.

Serves:
- GET /dashboard        — Jinja2 + htmx + Chart.js observability dashboard
- GET /api/metrics      — JSON metrics for programmatic access
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.db import get_metrics

router = APIRouter()

# Resolve templates directory relative to this file
_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    """Render the full observability dashboard."""
    metrics = await get_metrics()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        context={"metrics": metrics},
    )


@router.get("/api/metrics")
async def metrics_api() -> JSONResponse:
    """Return aggregate metrics as JSON."""
    data = await get_metrics()
    return JSONResponse(content=data)
