"""One-off, resumable EOD history warmup. Research only; no broker, Gmail or EODHD."""
from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from data_fetcher import HISTORY_CACHE_DIR, _history_cache_path, get_price_history
from universe_discovery import discover_dynamic_universe

LOG = Path(".cache/warmup_progress.json")
INVENTORY = Path(".cache/mx_inventory.csv")


def cache_bars(symbol):
    path = _history_cache_path(symbol)
    if not path.exists():
        return 0
    try:
        return len(pd.read_csv(path, usecols=[0]))
    except (OSError, ValueError, pd.errors.ParserError):
        return 0


def save_progress(data):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOG.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(LOG)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Resumable Yahoo EOD history warmup, no trading")
    parser.add_argument("--universe", type=int, choices=[250, 500, 1000], default=1000)
    parser.add_argument("--max-minutes", type=int, default=110)
    parser.add_argument("--delay", type=float, default=0.4)
    parser.add_argument("--min-bars", type=int, default=350)
    args = parser.parse_args(argv)
    if not 1 <= args.max_minutes <= 180 or not 0.2 <= args.delay <= 10:
        parser.error("max-minutes must be 1..180; delay must be 0.2..10")
    started = time.monotonic()
    deadline = started + args.max_minutes * 60
    print("Discovering MX/US symbols; Yahoo EOD only, no EODHD", flush=True)
    universe = discover_dynamic_universe(args.universe)
    symbols = universe["symbols"]
    # Mexico first. Keep provider discovery metadata separate from coverage.
    symbols.sort(key=lambda s: (not s.upper().endswith(".MX"), s))
    progress = {"started_utc": datetime.now(timezone.utc).isoformat(),
                "requested": args.universe, "discovered": len(symbols),
                "mx": universe["mx"], "us": universe["us"],
                "done": 0, "cached": 0, "downloaded": 0, "failed": 0,
                "results": {}}
    save_progress(progress)
    INVENTORY.parent.mkdir(parents=True, exist_ok=True)
    with INVENTORY.open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["symbol", "status", "bars", "reason"])
        for idx, symbol in enumerate(symbols, 1):
            if time.monotonic() >= deadline:
                print("Time budget reached; stopping cleanly.", flush=True)
                break
            before = cache_bars(symbol)
            if before >= args.min_bars:
                status, bars, reason = "CACHED", before, "already has sufficient rows"
                progress["cached"] += 1
            else:
                try:
                    # Force 2y to avoid mistakenly reusing a fresh 6mo cache.
                    history = get_price_history(symbol, period="2y", force_refresh=True)
                    bars = len(history) if history is not None else 0
                    status = "DOWNLOADED" if bars >= args.min_bars else "INSUFFICIENT"
                    reason = "" if status == "DOWNLOADED" else "provider returned fewer than minimum bars"
                    if status == "DOWNLOADED":
                        progress["downloaded"] += 1
                    else:
                        progress["failed"] += 1
                except Exception as exc:
                    status, bars, reason = "ERROR", 0, type(exc).__name__
                    progress["failed"] += 1
                time.sleep(args.delay)
            progress["done"] += 1
            progress["results"][symbol] = {"status": status, "bars": bars, "reason": reason}
            writer.writerow([symbol, status, bars, reason])
            out.flush()
            save_progress(progress)
            if idx % 25 == 0 or symbol.endswith(".MX"):
                print(f"[{idx}/{len(symbols)}] {symbol}: {status}, {bars} bars | cached={progress['cached']} downloaded={progress['downloaded']} insufficient/errors={progress['failed']}", flush=True)
    progress["elapsed_seconds"] = round(time.monotonic() - started, 2)
    progress["finished_utc"] = datetime.now(timezone.utc).isoformat()
    save_progress(progress)
    print(f"Finished: {progress['done']}/{len(symbols)} | {progress['elapsed_seconds']}s | .cache/history/ and {INVENTORY}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
