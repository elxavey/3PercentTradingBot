"""Manual morning report benchmark; no emails, orders or background scheduling."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from config import BREAKOUT_TEST_SYMBOLS, UNIVERSES
from tradepilot.morning_report import run_market_report


def main(argv=None):
    p = argparse.ArgumentParser(description="TradePilot market-separated EOD radar benchmark")
    p.add_argument("--universe", choices=("test20", "broad62"), default="test20")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--output", default="morning_radar_report.json")
    args = p.parse_args(argv)
    if args.limit is not None and not 1 <= args.limit <= 1000:
        p.error("--limit must be 1..1000")
    symbols = BREAKOUT_TEST_SYMBOLS if args.universe == "test20" else UNIVERSES["Broad MX + USA - 62 symbols"]
    if args.limit:
        symbols = symbols[:args.limit]
    report = run_market_report(symbols, progress=lambda i,n,s,state:
                               print(f"[{i}/{n}] {s}: {state}", flush=True))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    for market, data in report["markets"].items():
        print(f"{market}: reviewed={data['reviewed']} current={data['current']} "
              f"primary={len(data['primary'])} watch={len(data['watch'])}")
        for tier in ("primary", "watch"):
            for row in data[tier]:
                plan = row.get("trade_plan", {})
                print(f"  {tier:7} {row['symbol']:16} score={row['quality_score']:5.1f} "
                      f"close={row['reference_close']:.3f} trigger={row['breakout_trigger']:.3f} "
                      f"entry={plan.get('entry_reference')} target={plan.get('target_exit_reference')} "
                      f"stop={plan.get('stop_reference')}")
    print(f"Elapsed={report['elapsed_seconds']}s; projected 1000 sequential="
          f"{report['estimated_1000_seconds_linear']}s (rough extrapolation, not measured)")
    print(f"Saved: {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
