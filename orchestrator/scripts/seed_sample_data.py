"""Seed sample data into SQLite for dashboard testing.

Usage:
    cd orchestrator && python -m scripts.seed_sample_data
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db import init_db, get_db_path, _connect
from datetime import datetime, timezone, timedelta


async def seed() -> None:
    await init_db()
    db_path = get_db_path()
    print(f"Seeding database at: {db_path}")

    now = datetime.now(timezone.utc)

    issues = [
        {
            "issue_id": 1,
            "issue_node_id": "I_node_1",
            "title": "Session cookies not invalidated on logout",
            "category": "security",
            "status": "done",
            "pr_url": "https://github.com/victorlga/superset/pull/5",
            "created_at": (now - timedelta(days=5)).isoformat(),
            "updated_at": (now - timedelta(hours=2)).isoformat(),
            "planning_started_at": (now - timedelta(days=4, hours=20)).isoformat(),
            "building_started_at": (now - timedelta(days=4, hours=16)).isoformat(),
            "reviewing_started_at": (now - timedelta(days=4, hours=12)).isoformat(),
            "done_at": (now - timedelta(days=4, hours=10)).isoformat(),
        },
        {
            "issue_id": 2,
            "issue_node_id": "I_node_2",
            "title": "Guest users cannot sort embedded dashboard tables",
            "category": "security",
            "status": "done",
            "pr_url": "https://github.com/victorlga/superset/pull/6",
            "created_at": (now - timedelta(days=4)).isoformat(),
            "updated_at": (now - timedelta(hours=1)).isoformat(),
            "planning_started_at": (now - timedelta(days=3, hours=22)).isoformat(),
            "building_started_at": (now - timedelta(days=3, hours=18)).isoformat(),
            "reviewing_started_at": (now - timedelta(days=3, hours=14)).isoformat(),
            "done_at": (now - timedelta(days=3, hours=12)).isoformat(),
        },
        {
            "issue_id": 3,
            "issue_node_id": "I_node_3",
            "title": "HTML tags in error messages cause Bad Request",
            "category": "security",
            "status": "building",
            "created_at": (now - timedelta(days=3)).isoformat(),
            "updated_at": (now - timedelta(hours=3)).isoformat(),
            "planning_started_at": (now - timedelta(days=2, hours=20)).isoformat(),
            "building_started_at": (now - timedelta(days=2, hours=16)).isoformat(),
            "error_message": "Builder session timed out after 30 minutes",
        },
        {
            "issue_id": 4,
            "issue_node_id": "I_node_4",
            "title": "AUTH_USER_REGISTRATION enables public self-registration",
            "category": "security",
            "status": "planning",
            "created_at": (now - timedelta(days=2)).isoformat(),
            "updated_at": (now - timedelta(hours=4)).isoformat(),
            "planning_started_at": (now - timedelta(days=1, hours=20)).isoformat(),
        },
        {
            "issue_id": 5,
            "issue_node_id": "I_node_5",
            "title": "SQL injection via dashboard filter with apostrophes",
            "category": "high-impact-bug",
            "status": "backlog",
            "created_at": (now - timedelta(days=1)).isoformat(),
            "updated_at": (now - timedelta(hours=5)).isoformat(),
        },
    ]

    sessions = [
        {"issue_id": 1, "session_id": "devin-plan-001", "session_type": "planner", "status": "completed",
         "started_at": (now - timedelta(days=4, hours=20)).isoformat(),
         "finished_at": (now - timedelta(days=4, hours=19)).isoformat(), "duration_seconds": 3600},
        {"issue_id": 1, "session_id": "devin-build-001", "session_type": "builder", "status": "completed",
         "started_at": (now - timedelta(days=4, hours=16)).isoformat(),
         "finished_at": (now - timedelta(days=4, hours=13)).isoformat(), "duration_seconds": 10800},
        {"issue_id": 1, "session_id": "devin-review-001", "session_type": "reviewer", "status": "completed",
         "started_at": (now - timedelta(days=4, hours=12)).isoformat(),
         "finished_at": (now - timedelta(days=4, hours=11)).isoformat(), "duration_seconds": 3600},
        {"issue_id": 2, "session_id": "devin-plan-002", "session_type": "planner", "status": "completed",
         "started_at": (now - timedelta(days=3, hours=22)).isoformat(),
         "finished_at": (now - timedelta(days=3, hours=21)).isoformat(), "duration_seconds": 3600},
        {"issue_id": 2, "session_id": "devin-build-002", "session_type": "builder", "status": "completed",
         "started_at": (now - timedelta(days=3, hours=18)).isoformat(),
         "finished_at": (now - timedelta(days=3, hours=15)).isoformat(), "duration_seconds": 10800},
        {"issue_id": 2, "session_id": "devin-review-002", "session_type": "reviewer", "status": "completed",
         "started_at": (now - timedelta(days=3, hours=14)).isoformat(),
         "finished_at": (now - timedelta(days=3, hours=13)).isoformat(), "duration_seconds": 3600},
        {"issue_id": 3, "session_id": "devin-plan-003", "session_type": "planner", "status": "completed",
         "started_at": (now - timedelta(days=2, hours=20)).isoformat(),
         "finished_at": (now - timedelta(days=2, hours=19)).isoformat(), "duration_seconds": 3600},
        {"issue_id": 3, "session_id": "devin-build-003", "session_type": "builder", "status": "running",
         "started_at": (now - timedelta(days=2, hours=16)).isoformat(),
         "finished_at": None, "duration_seconds": None},
        {"issue_id": 4, "session_id": "devin-plan-004", "session_type": "planner", "status": "running",
         "started_at": (now - timedelta(days=1, hours=20)).isoformat(),
         "finished_at": None, "duration_seconds": None},
        {"issue_id": 3, "session_id": "devin-build-003-retry1", "session_type": "builder", "status": "error",
         "started_at": (now - timedelta(days=2, hours=18)).isoformat(),
         "finished_at": (now - timedelta(days=2, hours=17, minutes=30)).isoformat(), "duration_seconds": 1800},
        {"issue_id": 5, "session_id": "devin-scan-001", "session_type": "scanner", "status": "completed",
         "started_at": (now - timedelta(days=1, hours=12)).isoformat(),
         "finished_at": (now - timedelta(days=1, hours=11)).isoformat(), "duration_seconds": 3600},
    ]

    async with _connect() as db:
        for issue in issues:
            cols = list(issue.keys())
            vals = list(issue.values())
            placeholders = ", ".join(["?"] * len(cols))
            col_names = ", ".join(cols)
            await db.execute(
                f"INSERT OR REPLACE INTO issue_state ({col_names}) VALUES ({placeholders})",
                vals,
            )
        for sess in sessions:
            await db.execute(
                "INSERT INTO session_log (issue_id, session_id, session_type, status, started_at, finished_at, duration_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sess["issue_id"], sess["session_id"], sess["session_type"], sess["status"],
                 sess["started_at"], sess["finished_at"], sess["duration_seconds"]),
            )
        await db.commit()

    print(f"Seeded {len(issues)} issues and {len(sessions)} session logs.")


if __name__ == "__main__":
    asyncio.run(seed())
