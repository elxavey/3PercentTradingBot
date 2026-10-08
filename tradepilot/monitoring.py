"""Read-only operational dashboard data for TradePilot.

No worker control, no job recovery and no broker interaction.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tradepilot.operations import operational_status
from tradepilot.storage.database import DEFAULT_DB_PATH, database_connection, initialize_database
from tradepilot.storage.scan_repository import list_scans


def monitoring_snapshot(
    *, db_path: str | Path = DEFAULT_DB_PATH,
    limit: int = 20,
    stale_after_seconds: int = 180,
    at: datetime | None = None,
) -> dict:
    """Return job and scan summaries; no candidate payloads or sensitive config."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if stale_after_seconds <= 0:
        raise ValueError("stale_after_seconds must be positive")
    initialize_database(db_path)
    jobs = operational_status(
        db_path=db_path, limit=limit,
        stale_after_seconds=stale_after_seconds, at=at,
    )
    scans = list_scans(db_path=db_path, limit=limit)
    with database_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT j.id AS job_id, j.job_name, j.scheduled_for_utc,
                      j.started_at_utc, j.finished_at_utc, j.status,
                      j.error_message, j.heartbeat_at_utc,
                      s.id AS scan_id, s.universe_name,
                      s.elapsed_seconds, s.discovered_count,
                      s.pre_screen_count, s.quality_pass_count
               FROM job_runs j
               LEFT JOIN scan_runs s ON s.job_run_id = j.id
               ORDER BY j.started_at_utc DESC, j.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    heartbeat_by_id = {job["id"]: job["heartbeat_state"] for job in jobs}
    history = []
    for row in rows:
        entry = dict(row)
        entry["heartbeat_state"] = heartbeat_by_id.get(entry["job_id"], "UNKNOWN")
        history.append(entry)
    return {
        "generated_at_utc": (at or datetime.now(timezone.utc)).astimezone(
            timezone.utc
        ).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "latest_job": jobs[0] if jobs else None,
        "latest_scan": scans[0] if scans else None,
        "jobs": history,
        "scans": scans,
        "warnings": [
            "A stale heartbeat does not prove the worker stopped."
        ] if any(j["heartbeat_state"] in ("STALE_UNVERIFIED", "UNKNOWN")
                 and j["status"] == "RUNNING" for j in jobs) else [],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TradePilot read-only monitoring")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--stale-after-seconds", type=int, default=180)
    args = parser.parse_args(argv)
    try:
        result = monitoring_snapshot(
            db_path=args.db, limit=args.limit,
            stale_after_seconds=args.stale_after_seconds,
        )
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: cannot read monitoring data")
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
