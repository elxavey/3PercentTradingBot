"""Read-only Phase 3.9 universe expansion acceptance report.

Inspect persisted completed scan telemetry; never trigger a scan or mutate data.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from tradepilot.storage.database import DEFAULT_DB_PATH


def expansion_report(db_path: str | Path = DEFAULT_DB_PATH,
                     universe_name: str = "Broad MX + USA - 62 symbols") -> dict:
    path = Path(db_path)
    if not path.is_file():
        return {"state": "NO_DATABASE", "universe": universe_name}
    # SQLite read-only URI prevents implicit creation and accidental writes.
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        run = conn.execute(
            """SELECT id,universe_name,status,started_at_utc,finished_at_utc,
                      discovered_count,pre_screen_count,quality_pass_count,
                      elapsed_seconds
               FROM scan_runs WHERE universe_name=?
               ORDER BY started_at_utc DESC,id DESC LIMIT 1""",
            (universe_name,),
        ).fetchone()
        if run is None:
            return {"state": "NO_SCAN", "universe": universe_name}
        result = dict(run)
        rows = conn.execute(
            """SELECT symbol,quality_pass,opportunity_score
               FROM scan_candidates WHERE scan_run_id=?""",
            (run["id"],),
        ).fetchall()
        result["persisted_candidates"] = len(rows)
        result["persisted_quality_pass"] = sum(int(x["quality_pass"]) for x in rows)
        result["mx_candidates"] = sum(x["symbol"].endswith(".MX") for x in rows)
        result["us_candidates"] = len(rows) - result["mx_candidates"]
        result["state"] = (
            "READY_FOR_REVIEW"
            if run["status"] == "SUCCEEDED"
            and run["finished_at_utc"]
            and run["discovered_count"] is not None
            and run["pre_screen_count"] is not None
            and run["quality_pass_count"] is not None
            and run["quality_pass_count"] == result["persisted_quality_pass"]
            and 0 <= run["quality_pass_count"] <= run["pre_screen_count"] <= run["discovered_count"]
            and len(rows) <= run["discovered_count"]
            else "NEEDS_REVIEW"
        )
        result["note"] = (
            "Snapshot consistency only; not proof of market-data quality, "
            "freshness, strategy profitability or 62 successful symbols."
        )
        return result
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only expansion scan report")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--universe", default="Broad MX + USA - 62 symbols")
    args = parser.parse_args()
    print(json.dumps(expansion_report(args.db, args.universe), indent=2))


if __name__ == "__main__":
    main()
