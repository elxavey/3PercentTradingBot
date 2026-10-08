"""One-shot background scanner worker, independent of Streamlit.

No scheduling or order execution. SQLite is the source of truth for job state.
A RUNNING row blocks new jobs until an operator explicitly marks it interrupted;
this is conservative after power loss and avoids automatic duplicate scans.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from threading import Event, Thread
from tradepilot.operations import heartbeat

from config import APP_VERSION, DYNAMIC_UNIVERSES, UNIVERSES
from tradepilot.core.scanner_service import run_scan
from tradepilot.storage.database import (
    DEFAULT_DB_PATH, database_connection, initialize_database,
)
from tradepilot.storage.scan_repository import save_scan

JOB_NAME = "market_scan"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def claim_job(*, db_path: str | Path, scheduled_for_utc: str, config_version: str = APP_VERSION) -> str | None:
    """Atomically prevent simultaneous workers AND duplicate scheduled slots."""
    parsed = datetime.fromisoformat(scheduled_for_utc.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("scheduled_for_utc must include a timezone")
    scheduled_for_utc = parsed.astimezone(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")
    initialize_database(db_path)
    job_id = str(uuid4())
    with database_connection(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        active = conn.execute(
            "SELECT id FROM job_runs WHERE job_name=? AND status='RUNNING' LIMIT 1",
            (JOB_NAME,),
        ).fetchone()
        if active:
            return None
        try:
            conn.execute(
                """INSERT INTO job_runs
                   (id,job_name,scheduled_for_utc,started_at_utc,status,config_version)
                   VALUES (?,?,?,?,?,?)""",
                (job_id, JOB_NAME, scheduled_for_utc, utc_now(), "RUNNING", config_version),
            )
        except sqlite3.IntegrityError:
            return None
    return job_id


def finish_job(job_id: str, *, db_path: str | Path, status: str, error: str | None = None) -> None:
    if status not in ("SUCCEEDED", "FAILED", "INTERRUPTED"):
        raise ValueError("Unsupported terminal status")
    with database_connection(db_path) as conn:
        cursor = conn.execute(
            """UPDATE job_runs SET status=?,finished_at_utc=?,error_message=?
               WHERE id=? AND status='RUNNING'""",
            (status, utc_now(), error, job_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("Job is not RUNNING or no longer exists")


def interrupt_stale_job(*, db_path: str | Path, job_id: str) -> bool:
    """Manual recovery only: never guess whether another process is alive."""
    initialize_database(db_path)
    with database_connection(db_path) as conn:
        cursor = conn.execute(
            """UPDATE job_runs SET status='INTERRUPTED',finished_at_utc=?,
               error_message='Manually marked interrupted; verify no worker is active'
               WHERE id=? AND job_name=? AND status='RUNNING'""",
            (utc_now(), job_id, JOB_NAME),
        )
        return cursor.rowcount == 1


def execute_once(
    *,
    universe_name: str = "Test - 12 symbols",
    db_path: str | Path = DEFAULT_DB_PATH,
    scheduled_for_utc: str | None = None,
    scanner=run_scan,
    persist=save_scan,
) -> tuple[int, str | None]:
    """Return (exit code, job ID): 0 success, 2 already running/slot used, 1 error."""
    if universe_name in UNIVERSES:
        scan_kwargs = {"tickers": UNIVERSES[universe_name]}
    elif universe_name in DYNAMIC_UNIVERSES:
        scan_kwargs = {"dynamic_target": DYNAMIC_UNIVERSES[universe_name]}
    else:
        raise ValueError(f"Unknown universe: {universe_name}")
    slot = scheduled_for_utc or utc_now()
    # Validate explicit slots to avoid accidental mismatched local timestamps.
    parsed = datetime.fromisoformat(slot.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("scheduled_for_utc must include a timezone")
    slot = parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    job_id = claim_job(db_path=db_path, scheduled_for_utc=slot)
    if job_id is None:
        print("SKIPPED: another scan is RUNNING or this slot was already claimed.", file=sys.stderr)
        return 2, None
    # A lightweight independent heartbeat continues even during slow provider calls.
    # A missed heartbeat is diagnostic, never an automatic release of the lock.
    stop_heartbeat = Event()
    def pulse():
        while not stop_heartbeat.wait(30):
            try:
                if not heartbeat(job_id, db_path=db_path):
                    break
            except Exception:
                # Do not abort the scan because the health channel is unavailable.
                pass
    monitor = Thread(target=pulse, name="tradepilot-heartbeat", daemon=True)
    monitor.start()
    try:
        heartbeat(job_id, db_path=db_path)
        print(f"RUNNING job={job_id} universe={universe_name}", flush=True)
        outcome = scanner(**scan_kwargs)
        scan_id = persist(
            outcome, universe_name=universe_name,
            config_snapshot={"universe_mode": universe_name, "worker": True,
                             "app_version": APP_VERSION},
            db_path=db_path, job_run_id=job_id,
        )
    except Exception as exc:
        # Avoid printing provider tokens/credentials embedded in exception messages.
        error = f"{type(exc).__name__}: scan or persistence failed"
        stop_heartbeat.set()
        monitor.join(timeout=2)
        finish_job(job_id, db_path=db_path, status="FAILED", error=error)
        print(f"FAILED job={job_id} ({error})", file=sys.stderr)
        return 1, job_id
    stop_heartbeat.set()
    monitor.join(timeout=2)
    finish_job(job_id, db_path=db_path, status="SUCCEEDED")
    print(f"SUCCEEDED job={job_id} scan={scan_id}", flush=True)
    return 0, job_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TradePilot one-shot market scan worker")
    parser.add_argument("--universe", default="Test - 12 symbols",
                        choices=list(UNIVERSES) + list(DYNAMIC_UNIVERSES))
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--slot", help="UTC ISO-8601 unique job slot (optional)")
    parser.add_argument("--interrupt-job", help="Recover an abandoned RUNNING job after verifying its process stopped")
    parser.add_argument("--confirm-stopped", action="store_true", help="Confirm the previous worker process has stopped")
    args = parser.parse_args(argv)
    try:
        if args.interrupt_job:
            from tradepilot.recovery import recover_interrupted_job
            changed = recover_interrupted_job(db_path=args.db, job_id=args.interrupt_job,
                                              confirmed_stopped=args.confirm_stopped)
            print("INTERRUPTED" if changed else "NOT FOUND / NOT RUNNING")
            return 0 if changed else 2
        code, _ = execute_once(universe_name=args.universe, db_path=args.db,
                               scheduled_for_utc=args.slot)
        return code
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
