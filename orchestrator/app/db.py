"""SQLite database helpers using aiosqlite."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import aiosqlite

_DB_PATH: str | None = None


def _resolve_db_path() -> str:
    """Return the absolute path to the SQLite database file."""
    from app.config import settings

    # database_url looks like "sqlite+aiosqlite:///./data/orchestrator.db"
    raw = settings.database_url
    if raw.startswith("sqlite+aiosqlite:///"):
        raw = raw[len("sqlite+aiosqlite:///"):]
    elif raw.startswith("sqlite:///"):
        raw = raw[len("sqlite:///"):]
    return os.path.abspath(raw)


def get_db_path() -> str:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = _resolve_db_path()
    return _DB_PATH


def set_db_path(path: str | None) -> None:
    """Override the database path (useful for tests)."""
    global _DB_PATH
    _DB_PATH = path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS issue_state (
    issue_id            INTEGER PRIMARY KEY,
    issue_node_id       TEXT    NOT NULL,
    title               TEXT,
    category            TEXT    NOT NULL DEFAULT 'security',
    status              TEXT    NOT NULL DEFAULT 'backlog',
    planner_session     TEXT,
    builder_session     TEXT,
    reviewer_session    TEXT,
    plan_text           TEXT,
    pr_url              TEXT,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    planning_started_at TEXT,
    building_started_at TEXT,
    reviewing_started_at TEXT,
    done_at             TEXT,
    rebuild_count       INTEGER NOT NULL DEFAULT 0,
    error_message       TEXT
);

CREATE TABLE IF NOT EXISTS session_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id         INTEGER NOT NULL,
    session_id       TEXT    NOT NULL,
    session_type     TEXT    NOT NULL,
    status           TEXT    NOT NULL,
    started_at       TEXT    NOT NULL,
    finished_at      TEXT,
    duration_seconds INTEGER,
    FOREIGN KEY (issue_id) REFERENCES issue_state(issue_id)
);
"""


async def init_db() -> None:
    """Create tables if they don't exist."""
    path = get_db_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    async with aiosqlite.connect(path) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()


@asynccontextmanager
async def _connect() -> AsyncIterator[aiosqlite.Connection]:
    """Yield a fresh aiosqlite connection with Row factory."""
    db = await aiosqlite.connect(get_db_path())
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


def now_utc() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# issue_state helpers
# ---------------------------------------------------------------------------

async def get_issue(issue_id: int) -> dict[str, Any] | None:
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM issue_state WHERE issue_id = ?", (issue_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def upsert_issue(issue_id: int, **kwargs: Any) -> None:
    existing = await get_issue(issue_id)
    now = now_utc()
    if existing is None:
        cols = ["issue_id", "created_at", "updated_at"]
        vals: list[Any] = [issue_id, now, now]
        for k, v in kwargs.items():
            cols.append(k)
            vals.append(v)
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        async with _connect() as db:
            await db.execute(
                f"INSERT INTO issue_state ({col_names}) VALUES ({placeholders})",
                vals,
            )
            await db.commit()
    else:
        kwargs["updated_at"] = now
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [issue_id]
        async with _connect() as db:
            await db.execute(
                f"UPDATE issue_state SET {set_clause} WHERE issue_id = ?",
                vals,
            )
            await db.commit()


async def list_issues() -> list[dict[str, Any]]:
    """Return all issue_state rows ordered by issue_id."""
    async with _connect() as db:
        cursor = await db.execute("SELECT * FROM issue_state ORDER BY issue_id")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# session_log helpers
# ---------------------------------------------------------------------------

async def insert_session_log(
    issue_id: int,
    session_id: str,
    session_type: str,
    status: str = "running",
) -> int:
    now = now_utc()
    async with _connect() as db:
        cursor = await db.execute(
            "INSERT INTO session_log (issue_id, session_id, session_type, status, started_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (issue_id, session_id, session_type, status, now),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def update_session_log(
    session_id: str,
    status: str,
    duration_seconds: int | None = None,
) -> None:
    now = now_utc()
    async with _connect() as db:
        await db.execute(
            "UPDATE session_log SET status = ?, finished_at = ?, duration_seconds = ? "
            "WHERE session_id = ? AND finished_at IS NULL",
            (status, now, duration_seconds, session_id),
        )
        await db.commit()


async def list_active_sessions() -> list[dict[str, Any]]:
    """Return all session_log rows where status = 'running'.

    Used by the session tracker to know which Devin sessions to poll.
    """
    async with _connect() as conn:
        cursor = await conn.execute(
            "SELECT sl.*, ist.status AS issue_status "
            "FROM session_log sl "
            "JOIN issue_state ist ON sl.issue_id = ist.issue_id "
            "WHERE sl.status = 'running' "
            "ORDER BY sl.id"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def list_session_logs(issue_id: int | None = None) -> list[dict[str, Any]]:
    async with _connect() as db:
        if issue_id is not None:
            cursor = await db.execute(
                "SELECT * FROM session_log WHERE issue_id = ? ORDER BY id",
                (issue_id,),
            )
        else:
            cursor = await db.execute("SELECT * FROM session_log ORDER BY id DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------

async def get_metrics() -> dict[str, Any]:
    """Return dashboard metrics answering: "Is this system working?"

    Focused on three questions an engineering leader cares about:
    1. What is the status of active and completed tasks?
    2. Are sessions succeeding or failing?
    3. What just happened?
    """
    async with _connect() as db:
        # ---------------------------------------------------------------
        # 1. Pipeline status — issues by stage
        # ---------------------------------------------------------------

        cursor = await db.execute(
            "SELECT status, COUNT(*) as cnt FROM issue_state GROUP BY status"
        )
        status_counts: dict[str, int] = {}
        for row in await cursor.fetchall():
            status_counts[row["status"]] = row["cnt"]
        for s in ("backlog", "planning", "building", "reviewing", "done", "error"):
            status_counts.setdefault(s, 0)

        total_issues = sum(status_counts.values())

        # ---------------------------------------------------------------
        # 2. Session health — active, completed, failed
        # ---------------------------------------------------------------

        cursor = await db.execute(
            "SELECT session_type, COUNT(*) as cnt "
            "FROM session_log WHERE status = 'running' GROUP BY session_type"
        )
        active_by_type: dict[str, int] = {}
        active_total = 0
        for row in await cursor.fetchall():
            active_by_type[row["session_type"]] = row["cnt"]
            active_total += row["cnt"]

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM session_log"
        )
        total_sessions = (await cursor.fetchone())["cnt"]

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM session_log WHERE status = 'completed'"
        )
        completed_sessions = (await cursor.fetchone())["cnt"]

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM session_log WHERE status = 'failed'"
        )
        failed_sessions = (await cursor.fetchone())["cnt"]

        session_success_rate = (
            round(completed_sessions / total_sessions, 4) if total_sessions > 0 else 0.0
        )

        # ---------------------------------------------------------------
        # 3. Recent activity
        # ---------------------------------------------------------------

        cursor = await db.execute(
            "SELECT sl.*, ist.title as issue_title, ist.pr_url "
            "FROM session_log sl "
            "LEFT JOIN issue_state ist ON sl.issue_id = ist.issue_id "
            "ORDER BY sl.id DESC LIMIT 20"
        )
        recent_activity = [dict(r) for r in await cursor.fetchall()]

    return {
        "issues": status_counts,
        "total_issues": total_issues,
        "active_sessions": active_total,
        "active_sessions_by_type": active_by_type,
        "session_success_rate": session_success_rate,
        "total_sessions": total_sessions,
        "completed_sessions": completed_sessions,
        "failed_sessions": failed_sessions,
        "recent_activity": recent_activity,
    }
