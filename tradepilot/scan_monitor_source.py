"""Read-only historical scan candidate source for Opportunity Monitor.

No database initialization, writes, watchlist promotions or job scheduling.
"""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path

from tradepilot.storage.database import DEFAULT_DB_PATH


def scan_monitor_entries(scan_id: str, *, db_path: str | Path = DEFAULT_DB_PATH,
                         limit: int = 50) -> dict:
    if not isinstance(scan_id, str) or not scan_id.strip():
        raise ValueError("scan_id is required")
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    path = Path(db_path)
    if not path.is_file():
        raise ValueError("scan database not found")
    with_path = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(with_path, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        scan = conn.execute(
            "SELECT id,universe_name,status,finished_at_utc FROM scan_runs WHERE id=?",
            (scan_id.strip(),),
        ).fetchone()
        if scan is None or scan["status"] != "SUCCEEDED" or not scan["finished_at_utc"]:
            raise ValueError("scan must exist and have succeeded")
        candidates = conn.execute(
            """SELECT symbol,opportunity_score FROM scan_candidates
               WHERE scan_run_id=? AND quality_pass=1
                 AND opportunity_score IS NOT NULL
               ORDER BY opportunity_score DESC,symbol ASC""",
            (scan["id"],),
        ).fetchall()
        entries = []
        for item in candidates:
            try:
                score = float(item["opportunity_score"])
            except (ValueError, TypeError):
                continue
            if not math.isfinite(score):
                continue
            symbol = str(item["symbol"] or "").strip().upper()
            if not symbol:
                continue
            entries.append({
                "symbol": symbol,
                "market": "MX" if symbol.endswith(".MX") else "US",
                "state": "SCAN_PREVIEW",
                "opportunity_score": score,
            })
            if len(entries) >= limit:
                break
        return {
            "scan_id": scan["id"], "universe_name": scan["universe_name"],
            "finished_at_utc": scan["finished_at_utc"], "entries": entries,
        }
    finally:
        conn.close()
