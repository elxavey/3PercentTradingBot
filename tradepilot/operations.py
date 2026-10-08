"""Operational health inspection and heartbeat for one-shot workers.

A stale heartbeat is diagnostic only, NEVER proof a process is dead.
No automatic unlock, retry, order submission or scanner-rule changes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import json

from tradepilot.storage.database import DEFAULT_DB_PATH, database_connection, initialize_database

UTC = timezone.utc


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def heartbeat(job_id: str, *, db_path: str | Path = DEFAULT_DB_PATH) -> bool:
    """Update only a RUNNING job; cannot revive a finished job."""
    with database_connection(db_path) as conn:
        cursor = conn.execute(
            "UPDATE job_runs SET heartbeat_at_utc=? WHERE id=? AND status='RUNNING'",
            (now_utc(), job_id),
        )
        return cursor.rowcount == 1


def operational_status(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    stale_after_seconds: int = 180,
    limit: int = 10,
    at: datetime | None = None,
) -> list[dict]:
    if stale_after_seconds <= 0 or not 1 <= limit <= 100:
        raise ValueError("stale_after_seconds must be positive; limit must be 1..100")
    at = at or datetime.now(UTC)
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("at must be timezone-aware")
    initialize_database(db_path)
    with database_connection(db_path) as conn:
        rows = conn.execute(
            """SELECT id,job_name,scheduled_for_utc,started_at_utc,
                      finished_at_utc,status,error_message,heartbeat_at_utc
               FROM job_runs ORDER BY started_at_utc DESC, id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    keys = ("id", "job_name", "scheduled_for_utc", "started_at_utc",
            "finished_at_utc", "status", "error_message", "heartbeat_at_utc")
    result = []
    for row in rows:
        item = dict(zip(keys, row))
        item["heartbeat_state"] = "NOT_RUNNING"
        if item["status"] == "RUNNING":
            timestamp = item["heartbeat_at_utc"] or item["started_at_utc"]
            try:
                last = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                age = (at.astimezone(UTC) - last.astimezone(UTC)).total_seconds()
                item["heartbeat_state"] = (
                    "STALE_UNVERIFIED" if age > stale_after_seconds or age < -5 else "RECENT"
                )
            except (ValueError, TypeError):
                item["heartbeat_state"] = "UNKNOWN"
        result.append(item)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TradePilot read-only worker health")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--stale-after-seconds", type=int, default=180)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        rows = operational_status(db_path=args.db, stale_after_seconds=args.stale_after_seconds,
                                  limit=args.limit)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: cannot read operational status")
        return 1
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
