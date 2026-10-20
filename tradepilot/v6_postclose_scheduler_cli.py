"""Independent after-close V6 runner, preserving the existing opening scanner.

Run this from Windows Task Scheduler hourly (or manually). Calendar gates
enforce both exchanges' actual closes; no replay, broker orders, or manual
ticker selection. Scanner's persisted run is consumed by the V6 pipeline.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import exchange_calendars as xcals
from config import DYNAMIC_UNIVERSES
from tradepilot.worker import execute_once
from tradepilot.v6_postclose_pipeline_cli import run, save

UTC = timezone.utc
DEFAULT_UNIVERSE = "Dynamic MX + USA - 250 symbols"


def postclose_slot(now, *, delay_minutes=20, window_minutes=120, calendars=None):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone aware")
    if delay_minutes < 0 or window_minutes <= 0:
        raise ValueError("invalid slot settings")
    now = now.astimezone(UTC)
    calendars = calendars or {x: xcals.get_calendar(x) for x in ("XNYS", "XMEX")}
    closes = []
    for market in ("XNYS", "XMEX"):
        cal = calendars[market]
        if not cal.is_session(now.date()):
            return None
        closes.append(cal.session_close(now.date()).to_pydatetime().astimezone(UTC))
    scheduled = max(closes) + timedelta(minutes=delay_minutes)
    if not scheduled <= now < scheduled + timedelta(minutes=window_minutes):
        return None
    return scheduled


def tick(*, now, db="data/tradepilot.db", universe=DEFAULT_UNIVERSE,
         top=20, download=False, prefix=".cache/v6_postclose",
         calendars=None, worker=execute_once, pipeline=run):
    if universe not in DYNAMIC_UNIVERSES:
        raise ValueError("Only dynamic scanner universes are supported")
    slot = postclose_slot(now, calendars=calendars)
    if slot is None:
        return {"status": "NOT_DUE", "orders_sent": 0}
    slot_id = slot.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    code, job_id = worker(universe_name=universe, db_path=db,
                          scheduled_for_utc=slot_id)
    if code != 0:
        return {"status": "SCAN_SKIPPED" if code == 2 else "SCAN_FAILED",
                "job_id": job_id, "orders_sent": 0}
    result = pipeline(db, slot.date().isoformat(), top=top, download=download)
    result["job_id"] = job_id
    result["slot_utc"] = slot_id
    result["files"] = save(result, prefix)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="TradePilot V6 calendar-gated post-close scanner and research")
    p.add_argument("--db", default="data/tradepilot.db")
    p.add_argument("--universe", default=DEFAULT_UNIVERSE, choices=list(DYNAMIC_UNIVERSES))
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--prefix", default=".cache/v6_postclose")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    now = datetime.now(UTC)
    if a.dry_run:
        slot = postclose_slot(now)
        print(json.dumps({"status": "DUE" if slot else "NOT_DUE",
                          "slot_utc": slot.isoformat() if slot else None,
                          "universe": a.universe, "orders_sent": 0}, indent=2))
        return 0
    outcome = tick(now=now, db=a.db, universe=a.universe,
                   top=a.top, download=a.refresh, prefix=a.prefix)
    print(json.dumps({k: v for k, v in outcome.items() if k != "candidates"},
                     indent=2, default=str))
    return 1 if outcome["status"] == "SCAN_FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
