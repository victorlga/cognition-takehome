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
    """Return comprehensive metrics for the dashboard / API.

    Organised into four groups that answer what a VP of Engineering cares about:
    1. Pipeline Health  — "Is the system working right now?"
    2. Velocity & Efficiency — "Is this worth the investment?"
    3. Risk Posture — "Are we safer than yesterday?"
    4. Recent Activity — "What just happened?"
    """
    async with _connect() as db:
        # ---------------------------------------------------------------
        # 1. Pipeline Health
        # ---------------------------------------------------------------

        # Issues by status (pipeline funnel)
        cursor = await db.execute(
            "SELECT status, COUNT(*) as cnt FROM issue_state GROUP BY status"
        )
        status_counts: dict[str, int] = {}
        for row in await cursor.fetchall():
            status_counts[row["status"]] = row["cnt"]
        # Ensure all statuses present
        for s in ("backlog", "planning", "building", "reviewing", "done", "error"):
            status_counts.setdefault(s, 0)

        # Active sessions (running) with type breakdown
        cursor = await db.execute(
            "SELECT session_type, COUNT(*) as cnt "
            "FROM session_log WHERE status = 'running' GROUP BY session_type"
        )
        active_by_type: dict[str, int] = {}
        active_total = 0
        for row in await cursor.fetchall():
            active_by_type[row["session_type"]] = row["cnt"]
            active_total += row["cnt"]

        # Error rate: sessions that ended in error / total sessions
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM session_log"
        )
        total_sessions = (await cursor.fetchone())["cnt"]
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM session_log WHERE status = 'error'"
        )
        error_sessions = (await cursor.fetchone())["cnt"]
        error_rate = round(error_sessions / total_sessions, 4) if total_sessions > 0 else 0.0

        # Latest error messages
        cursor = await db.execute(
            "SELECT sl.session_id, sl.session_type, sl.issue_id, ist.title as issue_title, "
            "ist.error_message "
            "FROM session_log sl "
            "LEFT JOIN issue_state ist ON sl.issue_id = ist.issue_id "
            "WHERE sl.status = 'error' ORDER BY sl.id DESC LIMIT 5"
        )
        recent_errors = [dict(r) for r in await cursor.fetchall()]

        # ---------------------------------------------------------------
        # 2. Velocity & Efficiency
        # ---------------------------------------------------------------

        # Time-to-Remediation (TTR): median and p90 of (done_at - planning_started_at)
        cursor = await db.execute(
            "SELECT issue_id, title, planning_started_at, building_started_at, "
            "reviewing_started_at, done_at "
            "FROM issue_state WHERE status = 'done' AND planning_started_at IS NOT NULL "
            "AND done_at IS NOT NULL"
        )
        ttr_rows = await cursor.fetchall()
        ttr_values: list[float] = []
        ttr_per_issue: list[dict[str, Any]] = []
        for row in ttr_rows:
            planning_start = datetime.fromisoformat(row["planning_started_at"])
            done_time = datetime.fromisoformat(row["done_at"])
            total_hours = (done_time - planning_start).total_seconds() / 3600.0
            ttr_values.append(total_hours)
            # Per-stage breakdown
            stage_breakdown: dict[str, float | None] = {
                "planning_hours": None,
                "building_hours": None,
                "reviewing_hours": None,
            }
            if row["building_started_at"]:
                building_start = datetime.fromisoformat(row["building_started_at"])
                stage_breakdown["planning_hours"] = round(
                    (building_start - planning_start).total_seconds() / 3600.0, 2
                )
                if row["reviewing_started_at"]:
                    reviewing_start = datetime.fromisoformat(row["reviewing_started_at"])
                    stage_breakdown["building_hours"] = round(
                        (reviewing_start - building_start).total_seconds() / 3600.0, 2
                    )
                    stage_breakdown["reviewing_hours"] = round(
                        (done_time - reviewing_start).total_seconds() / 3600.0, 2
                    )
            ttr_per_issue.append({
                "issue_id": row["issue_id"],
                "title": row["title"],
                "total_hours": round(total_hours, 2),
                **stage_breakdown,
            })

        ttr_values.sort()
        median_ttr = round(_percentile(ttr_values, 50), 2) if ttr_values else None
        p90_ttr = round(_percentile(ttr_values, 90), 2) if ttr_values else None

        # Throughput: issues done grouped by date
        cursor = await db.execute(
            "SELECT DATE(done_at) as day, COUNT(*) as cnt "
            "FROM issue_state WHERE status = 'done' AND done_at IS NOT NULL "
            "GROUP BY DATE(done_at) ORDER BY day"
        )
        throughput_by_day = [
            {"date": row["day"], "count": row["cnt"]}
            for row in await cursor.fetchall()
        ]

        # Session success rate
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM session_log WHERE status = 'completed'"
        )
        completed_sessions = (await cursor.fetchone())["cnt"]
        session_success_rate = (
            round(completed_sessions / total_sessions, 4) if total_sessions > 0 else 0.0
        )

        # Devin compute cost per fix (avg session-minutes per completed issue)
        cursor = await db.execute(
            "SELECT SUM(duration_seconds) as total_secs, "
            "COUNT(DISTINCT issue_id) as issue_cnt "
            "FROM session_log WHERE status = 'completed' AND duration_seconds IS NOT NULL"
        )
        cost_row = await cursor.fetchone()
        total_compute_secs = cost_row["total_secs"] or 0
        issues_with_sessions = cost_row["issue_cnt"] or 0
        cost_per_fix_minutes = (
            round(total_compute_secs / 60.0 / issues_with_sessions, 1)
            if issues_with_sessions > 0
            else None
        )

        # ---------------------------------------------------------------
        # 3. Risk Posture
        # ---------------------------------------------------------------

        # Open vs. Closed trend (cumulative issues created vs done, by date)
        cursor = await db.execute(
            "SELECT DATE(created_at) as day, COUNT(*) as cnt "
            "FROM issue_state GROUP BY DATE(created_at) ORDER BY day"
        )
        created_by_day = [
            {"date": row["day"], "count": row["cnt"]}
            for row in await cursor.fetchall()
        ]
        cursor = await db.execute(
            "SELECT DATE(done_at) as day, COUNT(*) as cnt "
            "FROM issue_state WHERE status = 'done' AND done_at IS NOT NULL "
            "GROUP BY DATE(done_at) ORDER BY day"
        )
        closed_by_day = [
            {"date": row["day"], "count": row["cnt"]}
            for row in await cursor.fetchall()
        ]

        # Severity / category breakdown
        cursor = await db.execute(
            "SELECT category, COUNT(*) as cnt FROM issue_state GROUP BY category"
        )
        severity_breakdown = {row["category"]: row["cnt"] for row in await cursor.fetchall()}

        # Mean Time to First Response (MTFR)
        # Time from issue created_at to first session started_at
        cursor = await db.execute(
            "SELECT ist.issue_id, ist.created_at, MIN(sl.started_at) as first_session "
            "FROM issue_state ist "
            "INNER JOIN session_log sl ON ist.issue_id = sl.issue_id "
            "GROUP BY ist.issue_id"
        )
        mtfr_values: list[float] = []
        for row in await cursor.fetchall():
            created = datetime.fromisoformat(row["created_at"])
            first = datetime.fromisoformat(row["first_session"])
            mtfr_values.append((first - created).total_seconds() / 60.0)
        mean_mtfr_minutes = (
            round(sum(mtfr_values) / len(mtfr_values), 1) if mtfr_values else None
        )

        # Total issues
        total_issues = sum(status_counts.values())

        # ---------------------------------------------------------------
        # 4. Recent Activity
        # ---------------------------------------------------------------

        cursor = await db.execute(
            "SELECT sl.*, ist.title as issue_title, ist.pr_url "
            "FROM session_log sl "
            "LEFT JOIN issue_state ist ON sl.issue_id = ist.issue_id "
            "ORDER BY sl.id DESC LIMIT 20"
        )
        recent_activity = [dict(r) for r in await cursor.fetchall()]

    return {
        # Pipeline Health
        "active_sessions": active_total,
        "active_sessions_by_type": active_by_type,
        "issues": status_counts,
        "error_rate": error_rate,
        "recent_errors": recent_errors,
        # Velocity & Efficiency
        "median_time_to_remediation_hours": median_ttr,
        "p90_time_to_remediation_hours": p90_ttr,
        "ttr_per_issue": ttr_per_issue,
        "throughput_by_day": throughput_by_day,
        "session_success_rate": session_success_rate,
        "total_sessions": total_sessions,
        "completed_sessions": completed_sessions,
        "failed_sessions": error_sessions,
        "cost_per_fix_minutes": cost_per_fix_minutes,
        # Risk Posture
        "open_trend": created_by_day,
        "closed_trend": closed_by_day,
        "severity_breakdown": severity_breakdown,
        "mean_time_to_first_response_minutes": mean_mtfr_minutes,
        # Overview
        "total_issues": total_issues,
        # Recent Activity
        "recent_activity": recent_activity,
    }


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Return the *pct*-th percentile from an already-sorted list."""
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_values):
        return sorted_values[f]
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])
