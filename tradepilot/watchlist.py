"""Phase 2.1: deterministic, persisted research watchlist from completed scans.

This module does not fetch quotes, schedule jobs, place orders or generate
actionable trading signals. All writes require explicit invocation.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tradepilot.storage.database import DEFAULT_DB_PATH, database_connection, initialize_database

VALID_LIMITS = range(1, 51)


def _utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("scan timestamp must be timezone-aware")
    return dt.astimezone(timezone.utc)


def preview_watchlist(scan_id: str, *, db_path: str | Path = DEFAULT_DB_PATH, limit: int = 20) -> dict:
    """Preview top quality-passing candidates without mutating SQLite."""
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    initialize_database(db_path)
    with database_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        scan = conn.execute(
            "SELECT id, status, finished_at_utc, universe_name FROM scan_runs WHERE id = ?",
            (scan_id,),
        ).fetchone()
        if scan is None:
            raise ValueError("unknown scan id")
        if scan["status"] != "SUCCEEDED" or not scan["finished_at_utc"]:
            raise ValueError("only completed successful scans can update the watchlist")
        _utc(scan["finished_at_utc"])
        candidates = conn.execute(
            """SELECT symbol, exchange_code, opportunity_score
               FROM scan_candidates WHERE scan_run_id = ? AND quality_pass = 1
               AND opportunity_score IS NOT NULL
               ORDER BY opportunity_score DESC, symbol ASC LIMIT ?""",
            (scan_id, limit),
        ).fetchall()
    items = []
    for candidate in candidates:
        score = float(candidate["opportunity_score"])
        if not math.isfinite(score):
            continue
        symbol = candidate["symbol"].strip().upper()
        if not symbol:
            continue
        market = "MX" if symbol.endswith(".MX") else "US"
        items.append({"symbol": symbol, "market": market, "opportunity_score": score})
    return {
        "scan_id": scan["id"], "universe_name": scan["universe_name"],
        "observed_at_utc": scan["finished_at_utc"], "limit": limit, "items": items,
    }


def update_watchlist(
    scan_id: str, *, db_path: str | Path = DEFAULT_DB_PATH, limit: int = 20,
) -> dict:
    """Promote selected candidates; preserve others pending explicit expiry policy.

    Reject out-of-order scans so historical scans cannot silently rewrite the
    current watchlist. Replaying the same scan is idempotent.
    """
    preview = preview_watchlist(scan_id, db_path=db_path, limit=limit)
    observed = _utc(preview["observed_at_utc"])
    with database_connection(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        latest = conn.execute(
            "SELECT MAX(last_seen_at_utc) FROM watchlist_entries"
        ).fetchone()[0]
        if latest is not None and observed < _utc(latest):
            raise ValueError("historical scan cannot overwrite newer watchlist observations")
        changed = 0
        for item in preview["items"]:
            current = conn.execute(
                "SELECT last_seen_at_utc FROM watchlist_entries WHERE symbol=? AND market=?",
                (item["symbol"], item["market"]),
            ).fetchone()
            if current is not None and observed < _utc(current[0]):
                raise ValueError("scan is older than existing symbol observation")
            conn.execute(
                """INSERT INTO watchlist_entries
                   (symbol,market,state,first_seen_at_utc,last_seen_at_utc,last_scan_run_id)
                   VALUES (?,?,'WATCHING',?,?,?)
                   ON CONFLICT(symbol,market) DO UPDATE SET
                     state='WATCHING',
                     last_seen_at_utc=excluded.last_seen_at_utc,
                     last_scan_run_id=excluded.last_scan_run_id""",
                (item["symbol"], item["market"], preview["observed_at_utc"],
                 preview["observed_at_utc"], scan_id),
            )
            changed += 1
    return {"scan_id": scan_id, "promoted_or_refreshed": changed,
            "note": "Non-selected entries retained until an explicit expiry policy is implemented."}


def list_watchlist(*, db_path: str | Path = DEFAULT_DB_PATH) -> list[dict]:
    initialize_database(db_path)
    with database_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT w.symbol,w.market,w.state,w.first_seen_at_utc,
                      w.last_seen_at_utc,w.last_scan_run_id,
                      c.opportunity_score
               FROM watchlist_entries w
               LEFT JOIN scan_candidates c
                 ON c.scan_run_id=w.last_scan_run_id AND c.symbol=w.symbol
               ORDER BY c.opportunity_score DESC, w.symbol ASC"""
        ).fetchall()
        return [dict(row) for row in rows]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TradePilot research watchlist")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--scan-id", help="Saved successful scan to preview or apply")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--apply", action="store_true", help="Explicitly persist watchlist")
    args = parser.parse_args(argv)
    try:
        if args.apply and not args.scan_id:
            parser.error("--apply requires --scan-id")
        if args.scan_id:
            result = (update_watchlist if args.apply else preview_watchlist)(
                args.scan_id, db_path=args.db, limit=args.limit
            )
        else:
            result = list_watchlist(db_path=args.db)
    except (ValueError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
