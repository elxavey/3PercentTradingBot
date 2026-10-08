"""Explicit, conservative recovery of an abandoned worker.

A stale heartbeat does NOT establish that a process is dead. Recovery requires
operator verification and explicit confirmation. No automatic retries.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from tradepilot.storage.database import DEFAULT_DB_PATH, database_connection, initialize_database

UTC = timezone.utc


def recover_interrupted_job(
    job_id: str,
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    confirmed_stopped: bool = False,
    min_age_seconds: int = 180,
    at: datetime | None = None,
) -> bool:
    """Compare-and-swap the observed heartbeat after explicit operator verification.

    The lock remains untouched on failed confirmation, fresh heartbeat, or
    concurrent heartbeat update. The old scheduled slot remains reserved.
    """
    if not confirmed_stopped:
        raise ValueError("Confirm the worker process is stopped before recovery")
    if min_age_seconds <= 0:
        raise ValueError("min_age_seconds must be positive")
    at = at or datetime.now(UTC)
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("at must be timezone-aware")
    if not job_id or not job_id.strip():
        raise ValueError("job_id is required")
    initialize_database(db_path)
    with database_connection(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT heartbeat_at_utc,started_at_utc FROM job_runs
               WHERE id=? AND job_name='market_scan' AND status='RUNNING'""",
            (job_id,),
        ).fetchone()
        if row is None:
            return False
        heartbeat_value, started = row
        timestamp = heartbeat_value or started
        try:
            observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if observed.tzinfo is None or observed.utcoffset() is None:
                return False
        except (ValueError, TypeError):
            return False
        age = (at.astimezone(UTC) - observed.astimezone(UTC)).total_seconds()
        if age < min_age_seconds:
            return False
        # BEGIN IMMEDIATE serializes against heartbeat writes. A fresh
        # heartbeat that committed first will be observed and rejected.
        cursor = conn.execute(
            """UPDATE job_runs SET status='INTERRUPTED',
                   finished_at_utc=?,error_message=?
               WHERE id=? AND status='RUNNING'""",
            (
                at.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                "Operator confirmed process stopped; stale heartbeat; manual recovery",
                job_id,
            ),
        )
        return cursor.rowcount == 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TradePilot operator-confirmed recovery")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--min-age-seconds", type=int, default=180)
    parser.add_argument("--confirm-stopped", action="store_true",
                        help="I verified the worker is no longer running")
    args = parser.parse_args(argv)
    try:
        recovered = recover_interrupted_job(
            args.job_id, db_path=args.db,
            min_age_seconds=args.min_age_seconds,
            confirmed_stopped=args.confirm_stopped,
        )
    except Exception as exc:
        print(f"RECOVERY BLOCKED: {type(exc).__name__}: {exc}")
        return 1
    print("INTERRUPTED: prior slot remains reserved" if recovered
          else "NOT RECOVERED: job missing, terminal, or heartbeat not old enough")
    return 0 if recovered else 2


if __name__ == "__main__":
    raise SystemExit(main())
