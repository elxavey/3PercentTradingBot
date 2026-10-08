"""Exchange-calendar aware scanner scheduler (US XNYS + Mexico XMEX).

A combined-universe scan is eligible only when BOTH markets share an open
session. Its one daily slot is 15 minutes after the later exchange open.
We use exchange_calendars' actual UTC open/close instants (holidays, early
closes, timezone/DST), never hardcoded US/Mexico clock offsets.

No broker orders, no intraday freshness claims, no automatic crash replay.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import sys
import time
from pathlib import Path

from tradepilot.storage.database import DEFAULT_DB_PATH
from tradepilot.worker import execute_once

UTC = timezone.utc
DEFAULT_UNIVERSE = "Test - 12 symbols"
MARKETS = ("XNYS", "XMEX")


@dataclass(frozen=True)
class ScheduledSlot:
    scheduled_for_utc: datetime
    latest_start_utc: datetime
    market_open_utc: datetime
    market_close_utc: datetime
    markets: tuple[str, ...]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An offset-aware datetime is required")
    return value.astimezone(UTC)


def calendar_slot(
    day,
    *,
    delay_minutes: int = 15,
    max_lateness_minutes: int = 30,
    calendars=None,
) -> ScheduledSlot | None:
    """Return a single combined-market slot, or None if either is closed.

    The window is constrained by the EARLIEST exchange close; short sessions
    that cannot fit the delay/window are rejected rather than backfilled.
    """
    if delay_minutes < 0 or max_lateness_minutes < 0:
        raise ValueError("Delays must be nonnegative")
    if calendars is None:
        import exchange_calendars as xcals
        calendars = {market: xcals.get_calendar(market) for market in MARKETS}
    opens, closes = [], []
    for market in MARKETS:
        calendar = calendars[market]
        if not calendar.is_session(day):
            return None
        opens.append(calendar.session_open(day).to_pydatetime().astimezone(UTC))
        closes.append(calendar.session_close(day).to_pydatetime().astimezone(UTC))
    later_open, earlier_close = max(opens), min(closes)
    planned = later_open + timedelta(minutes=delay_minutes)
    latest = min(planned + timedelta(minutes=max_lateness_minutes), earlier_close)
    if planned >= earlier_close or latest <= planned:
        return None
    return ScheduledSlot(planned, latest, later_open, earlier_close, MARKETS)


def due_slot(
    now: datetime,
    *,
    delay_minutes: int = 15,
    max_lateness_minutes: int = 30,
    calendars=None,
) -> ScheduledSlot | None:
    """Only today's UTC session slot, only while its execution window is open.

    This intentionally does not backfill yesterday's missed scans after sleep.
    """
    now = _utc(now)
    slot = calendar_slot(
        now.date(), delay_minutes=delay_minutes,
        max_lateness_minutes=max_lateness_minutes, calendars=calendars,
    )
    if slot is None or not slot.scheduled_for_utc <= now < slot.latest_start_utc:
        return None
    return slot


def tick(
    *,
    now: datetime,
    universe_name: str = DEFAULT_UNIVERSE,
    db_path: str | Path = DEFAULT_DB_PATH,
    delay_minutes: int = 15,
    max_lateness_minutes: int = 30,
    calendars=None,
    worker=execute_once,
    dry_run: bool = False,
) -> int:
    """Evaluate one moment. 0=no due job/success, 1=worker failure, 2=duplicate."""
    slot = due_slot(
        now, delay_minutes=delay_minutes,
        max_lateness_minutes=max_lateness_minutes, calendars=calendars,
    )
    if slot is None:
        print("NOT DUE: both markets must be open and within the scheduled window.")
        return 0
    slot_iso = slot.scheduled_for_utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if dry_run:
        print(f"DRY RUN: due slot={slot_iso} markets={','.join(slot.markets)}")
        return 0
    code, _ = worker(
        universe_name=universe_name, db_path=db_path, scheduled_for_utc=slot_iso,
    )
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TradePilot MX+US market-aware scheduler")
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--delay-minutes", type=int, default=15)
    parser.add_argument("--max-lateness-minutes", type=int, default=30)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--loop", action="store_true", help="Run continuously until Ctrl+C")
    parser.add_argument("--dry-run", action="store_true", help="Show due slot; never run scanner")
    args = parser.parse_args(argv)
    if args.poll_seconds < 60:
        parser.error("--poll-seconds must be at least 60")
    try:
        while True:
            result = tick(
                now=datetime.now(UTC), universe_name=args.universe,
                db_path=args.db, delay_minutes=args.delay_minutes,
                max_lateness_minutes=args.max_lateness_minutes,
                dry_run=args.dry_run,
            )
            if not args.loop:
                return 0 if result == 2 else result
            if result == 1:
                print("Worker failed; scheduler continuing without replaying the same slot.", file=sys.stderr)
            time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        print("Scheduler stopped.")
        return 0
    except Exception as exc:
        print(f"Scheduler error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
