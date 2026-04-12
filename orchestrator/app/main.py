"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.poller import start_polling_loop
from app.webhook import router as webhook_router
from app.dashboard import router as dashboard_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialise the database and start the background poller."""
    logger.info("Initialising database …")
    await init_db()
    logger.info("Database ready.")

    poll_task: asyncio.Task[None] | None = None
    if settings.polling_enabled:
        logger.info("Starting background poller (interval=%ds) …", settings.poll_interval_seconds)
        poll_task = asyncio.create_task(start_polling_loop())
    else:
        logger.info("Polling disabled — webhook-only mode.")

    yield

    if poll_task is not None and not poll_task.done():
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass
        logger.info("Poller stopped.")


app = FastAPI(
    title="Vulnerability Remediation Orchestrator",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the dashboard and external callers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(webhook_router)
app.include_router(dashboard_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Simple health-check endpoint."""
    return {"status": "ok"}
