"""Phase 2.4: one-shot scheduled watchlist research, opt-in Windows task.

One daily combined-exchange slot, 60 minutes after the later opening.
SQLite reserves the slot atomically. No replay, no automatic watchlist state
changes, no broker orders. Manual recovery is required for interrupted jobs.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from tradepilot.scheduler import calendar_slot
from tradepilot.storage.database import DEFAULT_DB_PATH, database_connection, initialize_database
from tradepilot.watchlist_refresh import refresh

JOB_NAME = "watchlist_refresh"
UTC = timezone.utc


def due_watchlist_slot(now: datetime, *, delay_minutes: int = 60,
                       max_lateness_minutes: int = 30, calendars=None):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware clock required")
    if delay_minutes < 0 or max_lateness_minutes <= 0:
        raise ValueError("invalid scheduling window")
    now = now.astimezone(UTC)
    slot = calendar_slot(now.date(), delay_minutes=delay_minutes,
                         max_lateness_minutes=max_lateness_minutes,
                         calendars=calendars)
    if slot and slot.scheduled_for_utc <= now < slot.latest_start_utc:
        return slot
    return None


def _stamp(now: datetime) -> str:
    return now.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def tick(*, now: datetime, db_path: str | Path = DEFAULT_DB_PATH,
         limit: int = 50, dry_run: bool = False,
         runner=refresh, calendars=None) -> dict:
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    slot = due_watchlist_slot(now, calendars=calendars)
    if slot is None:
        return {"status": "NOT_DUE"}
    slot_id = _stamp(slot.scheduled_for_utc)
    if dry_run:
        return {"status": "DRY_RUN", "scheduled_for_utc": slot_id}
    initialize_database(db_path)
    job_id = str(uuid4())
    with database_connection(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        active = conn.execute(
            "SELECT id FROM job_runs WHERE status='RUNNING' LIMIT 1"
        ).fetchone()
        if active:
            return {"status": "SKIPPED", "reason": "ANOTHER_JOB_RUNNING"}
        try:
            conn.execute(
                """INSERT INTO job_runs
                   (id,job_name,scheduled_for_utc,started_at_utc,status,config_version)
                   VALUES (?,?,?,?,?,?)""",
                (job_id, JOB_NAME, slot_id, _stamp(now), "RUNNING", "phase-2.4"),
            )
        except sqlite3.IntegrityError:
            return {"status": "SKIPPED", "reason": "SLOT_ALREADY_CLAIMED"}
    try:
        result = runner(db_path=db_path, limit=limit)
        if result["status"] not in ("SUCCEEDED", "SKIPPED"):
            raise RuntimeError("unexpected refresh status")
    except Exception as exc:
        with database_connection(db_path) as conn:
            conn.execute(
                """UPDATE job_runs SET status='FAILED',finished_at_utc=?,error_message=?
                   WHERE id=? AND status='RUNNING'""",
                (_stamp(datetime.now(UTC)), f"{type(exc).__name__}: refresh failed", job_id),
            )
        return {"status": "FAILED", "job_id": job_id, "error_type": type(exc).__name__}
    with database_connection(db_path) as conn:
        conn.execute(
            """UPDATE job_runs SET status=?,finished_at_utc=?
               WHERE id=? AND status='RUNNING'""",
            ("SUCCEEDED" if result["status"] == "SUCCEEDED" else "SKIPPED",
             _stamp(datetime.now(UTC)), job_id),
        )
    return {"status": result["status"], "job_id": job_id,
            "scan_id": result.get("scan_id"),
            "evaluated": result.get("evaluated", 0)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TradePilot scheduled watchlist research")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = tick(now=datetime.now(UTC), db_path=args.db,
                      limit=args.limit, dry_run=args.dry_run)
        import json
        print(json.dumps(result, indent=2))
        return 1 if result["status"] == "FAILED" else 0
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
