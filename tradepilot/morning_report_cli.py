"""Manual morning report benchmark; no emails, orders or background scheduling."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from config import BREAKOUT_TEST_SYMBOLS, UNIVERSES
from tradepilot.morning_report import run_market_report
from universe_discovery import discover_dynamic_universe
from tradepilot.bmv_universe import load_bmv_research_symbols
from time import perf_counter


def main(argv=None):
    p = argparse.ArgumentParser(description="TradePilot market-separated EOD radar benchmark")
    p.add_argument("--universe", choices=("test20", "broad62", "dynamic250", "dynamic500", "dynamic1000"), default="test20")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--output", default="morning_radar_report.json")
    p.add_argument("--include-bmv-research", action="store_true", help="Opt-in unverified BMV research candidates")
    p.add_argument("--bmv-file", default=".cache/mx_bmv_candidate_validation.csv")
    args = p.parse_args(argv)
    if args.limit is not None and not 1 <= args.limit <= 1000:
        p.error("--limit must be 1..1000")
    discovery = None
    if args.universe.startswith("dynamic"):
        target = int(args.universe.removeprefix("dynamic"))
        print(f"Discovering {target} equities from Yahoo (no EODHD)...", flush=True)
        started = perf_counter()
        discovery = discover_dynamic_universe(target)
        discovery["measured_wall_seconds"] = round(perf_counter() - started, 3)
        symbols = discovery["symbols"]
        print(f"Discovered {len(symbols)}/{target}: MX={discovery['mx']} US={discovery['us']} in {discovery['measured_wall_seconds']}s", flush=True)
        if not symbols:
            p.error("Yahoo discovery returned no symbols; refusing empty scan")
    else:
        symbols = BREAKOUT_TEST_SYMBOLS if args.universe == "test20" else UNIVERSES["Broad MX + USA - 62 symbols"]
    bmv_overlay = None
    if args.include_bmv_research:
        try:
            bmv_symbols, bmv_counts = load_bmv_research_symbols(args.bmv_file)
        except (FileNotFoundError, ValueError) as exc:
            p.error(str(exc))
        base_count = len(symbols)
        symbols = list(dict.fromkeys(list(symbols) + bmv_symbols))
        bmv_overlay = {"candidates_selected": len(bmv_symbols),
                       "new_symbols_added": len(symbols) - base_count,
                       "counts": bmv_counts, "mapping_verified": False, "research_only": True}
        print(f"BMV research overlay: {len(bmv_symbols)} candidates, {bmv_overlay['new_symbols_added']} new to scan (mapping unverified)", flush=True)
    if args.limit:
        symbols = symbols[:args.limit]
    report = run_market_report(symbols, progress=lambda i,n,s,state:
                               print(f"[{i}/{n}] {s}: {state}", flush=True))
    report["universe"] = args.universe
    report["discovery"] = discovery
    report["bmv_research_overlay"] = bmv_overlay
    report["coverage_pct"] = round(100 * report["completed"] / len(symbols), 2) if symbols else 0
    report["total_wall_seconds_including_discovery"] = round(report["elapsed_seconds"] + (discovery["measured_wall_seconds"] if discovery else 0), 3)
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
    print(f"Coverage={report['coverage_pct']}% | total including discovery={report['total_wall_seconds_including_discovery']}s")
    print(f"Elapsed={report['elapsed_seconds']}s; projected 1000 sequential="
          f"{report['estimated_1000_seconds_linear']}s (rough extrapolation, not measured)")
    print(f"Saved: {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
