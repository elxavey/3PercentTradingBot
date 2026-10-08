"""Manual watchlist-only research refresh; no automatic trades."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tradepilot.core.scanner_service import run_scan
from tradepilot.daily_freshness import assess_daily_history
from tradepilot.storage.database import DEFAULT_DB_PATH, database_connection, initialize_database
from tradepilot.storage.scan_repository import save_scan
from tradepilot.watchlist import list_watchlist

UNIVERSE_NAME = "Watchlist incremental research"


def preview_refresh(*, db_path: str | Path = DEFAULT_DB_PATH, limit: int = 50) -> dict:
    if not 1 <= limit <= 50:
        raise ValueError("limit must be 1 through 50")
    entries = list_watchlist(db_path=db_path)
    symbols = [r["symbol"] for r in entries if r["state"] in ("WATCHING", "PROMOTED")]
    if len(symbols) > limit:
        raise ValueError("active watchlist exceeds limit; no symbols were scanned")
    if len(symbols) != len(set(symbols)):
        raise ValueError("duplicate active symbol")
    return {"symbols": symbols, "excluded_terminal": len(entries) - len(symbols)}


def refresh(*, db_path: str | Path = DEFAULT_DB_PATH, limit: int = 50,
            scanner=run_scan, saver=save_scan) -> dict:
    plan = preview_refresh(db_path=db_path, limit=limit)
    if not plan["symbols"]:
        return {"status": "SKIPPED", "reason": "EMPTY_WATCHLIST", **plan}
    outcome = scanner(tickers=plan["symbols"], etf_tickers=[])
    as_of = datetime.now(timezone.utc)
    evidence = {}
    for row in (outcome.universe_result.get("passed", []) +
                outcome.universe_result.get("excluded", [])):
        symbol = row.get("ticker")
        if symbol in plan["symbols"]:
            evidence[symbol] = assess_daily_history(
                row.get("history"), market="MX" if symbol.endswith(".MX") else "US",
                as_of_utc=as_of,
            )
    for symbol in plan["symbols"]:
        evidence.setdefault(symbol, {"status": "UNKNOWN", "reason": "NO_PRESCREEN_EVIDENCE",
                                     "latest_bar_session": None,
                                     "expected_completed_session": None})
    scan_id = saver(
        outcome, universe_name=UNIVERSE_NAME, db_path=db_path,
        config_snapshot={"phase": "2.3", "symbols": plan["symbols"],
                         "freshness_verified": False, "research_only": True,
                         "daily_session_freshness": evidence,
                         "freshness_assessed_at_utc": as_of.isoformat()},
    )
    return {"status": "SUCCEEDED", "scan_id": scan_id,
            "evaluated": len(outcome.results),
            "quality_passed": len(outcome.quality_passed),
            "freshness_verified": False,
            "daily_freshness_counts": {state: sum(x["status"] == state for x in evidence.values())
                                       for state in ("FRESH", "STALE", "UNKNOWN")}, **plan}



def compare_refresh(scan_id: str, *, db_path: str | Path = DEFAULT_DB_PATH) -> dict:
    """Read-only comparison against the watchlist's last applied scan.

    observed_at_utc records database ingestion, NOT quote/bar observation time.
    Missing candidates remain unknown, never a failed Quality Gate.
    """
    initialize_database(db_path)
    with database_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        run = conn.execute(
            """SELECT id, status, universe_name, finished_at_utc, elapsed_seconds, config_snapshot_json
               FROM scan_runs WHERE id=?""", (scan_id,),
        ).fetchone()
        if run is None or run["status"] != "SUCCEEDED" or not run["finished_at_utc"]:
            raise ValueError("comparison requires a successful completed scan")
        if run["universe_name"] != UNIVERSE_NAME:
            raise ValueError("comparison requires an incremental watchlist scan")
        candidates = conn.execute(
            """SELECT symbol, exchange_code, opportunity_score, quality_pass,
                      observed_at_utc, price_source
               FROM scan_candidates WHERE scan_run_id=?""", (scan_id,),
        ).fetchall()
        previous = conn.execute(
            """SELECT w.symbol, w.market, w.state, w.last_seen_at_utc,
                      w.last_scan_run_id, c.opportunity_score AS previous_score
               FROM watchlist_entries w
               LEFT JOIN scan_candidates c
                 ON c.scan_run_id=w.last_scan_run_id AND c.symbol=w.symbol
               WHERE w.state IN ('WATCHING','PROMOTED')"""
        ).fetchall()
    snapshot = json.loads(run["config_snapshot_json"])
    daily_evidence = snapshot.get("daily_session_freshness", {})
    by_symbol = {r["symbol"]: dict(r) for r in candidates}
    rows = []
    for old in previous:
        new = by_symbol.get(old["symbol"])
        current_score = new["opportunity_score"] if new else None
        previous_score = old["previous_score"]
        delta = (round(float(current_score) - float(previous_score), 2)
                 if current_score is not None and previous_score is not None else None)
        freshness = daily_evidence.get(old["symbol"], {}) if new else {}
        rows.append({
            "symbol": old["symbol"], "market": old["market"], "state": old["state"],
            "previous_score": previous_score, "new_score": current_score,
            "delta": delta,
            "quality_gate": ("PASS" if new["quality_pass"] else "FAIL") if new else "NOT_EVALUATED",
            "baseline_scan_id": old["last_scan_run_id"],
            "baseline_at_utc": old["last_seen_at_utc"],
            "ingested_at_utc": new["observed_at_utc"] if new else None,
            "market_data_freshness": freshness.get("status", "UNKNOWN"),
            "freshness_reason": freshness.get("reason", "NO_DAILY_SESSION_EVIDENCE"),
            "latest_bar_session": freshness.get("latest_bar_session"),
            "expected_completed_session": freshness.get("expected_completed_session"),
        })
    return {
        "scan_id": scan_id, "finished_at_utc": run["finished_at_utc"],
        "elapsed_seconds": run["elapsed_seconds"],
        "freshness_verified": False,
        "freshness_note": (
            "Daily-history freshness compares session dates against the last "
            "completed exchange session. FRESH does NOT mean a live quote. "
            "Candidate observed_at_utc is ingestion time, not quote time."
        ),
        "items": rows,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    result = (refresh if args.run else preview_refresh)(
        db_path=args.db, limit=args.limit
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
