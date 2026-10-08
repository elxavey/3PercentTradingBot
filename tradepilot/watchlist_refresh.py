"""Manual watchlist-only research refresh; no automatic trades."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tradepilot.core.scanner_service import run_scan
from tradepilot.storage.database import DEFAULT_DB_PATH
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
    scan_id = saver(
        outcome, universe_name=UNIVERSE_NAME, db_path=db_path,
        config_snapshot={"phase": "2.3", "symbols": plan["symbols"],
                         "freshness_verified": False, "research_only": True},
    )
    return {"status": "SUCCEEDED", "scan_id": scan_id,
            "evaluated": len(outcome.results),
            "quality_passed": len(outcome.quality_passed),
            "freshness_verified": False, **plan}


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
