"""Shared test fixtures."""

from __future__ import annotations

import os
import tempfile

import pytest
import pytest_asyncio

from app import db


@pytest_asyncio.fixture(autouse=True)
async def _use_temp_db(tmp_path):
    """Use a temporary SQLite database for every test."""
    db_path = str(tmp_path / "test.db")
    db.set_db_path(db_path)
    await db.init_db()
    yield
    db.set_db_path(None)  # type: ignore[arg-type]
