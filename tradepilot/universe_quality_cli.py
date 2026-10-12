"""Audit both radar strategies and market representation without approving BMV mappings."""
from __future__ import annotations
import argparse
import json
from collections import Counter
from pathlib import Path


def audit(report):
    results = report.get("results") or []
    rebounds = report.get("rebound_results") or []
    def market_rows(rows, market):
        return [r for r in rows if str(r.get("symbol", "")).endswith(".MX") == (market == "MX")]
    def strategy_detail(rows):
        return {
            "states": dict(Counter(r.get("state", "UNKNOWN") for r in rows)),
            "risk_assessments": dict(Counter(r.get("risk_assessment", "NOT_EVALUATED") for r in rows)),
            "confirmed": sum(r.get("state") in ("CONFIRMED_RESEARCH", "REBOUND_CONFIRMED_RESEARCH") for r in rows),
            "entry_reference_below_close": sum(
                isinstance((r.get("trade_plan") or {}).get("entry_reference"), (int, float))
                and isinstance(r.get("reference_close"), (int, float))
                and r["trade_plan"]["entry_reference"] < r["reference_close"] for r in rows)}
    def detail(rows):
        return {"reviewed": len(rows),
                "current": sum((r.get("session_quality") or {}).get("state") == "CURRENT" for r in rows),
                "rejected": sum(r.get("state") in ("REJECT", "ERROR") for r in rows),
                "rejection_reasons": dict(Counter(r.get("reason", "UNKNOWN") for r in rows
                                                  if r.get("state") in ("REJECT", "ERROR")))}
    mx, us = market_rows(results, "MX"), market_rows(results, "US")
    duplicates = [symbol for symbol, count in Counter(r.get("symbol") for r in results).items()
                  if symbol and count > 1]
    return {"requested": report.get("requested"), "MX": detail(mx), "US": detail(us),
            "mexico_share_pct": round(100*len(mx)/len(results), 2) if results else None,
            "mexico_shortfall_to_20pct": max(0, (report.get("requested") or len(results))//5-len(mx)),
            "duplicates": duplicates[:30],
            "strategies": {
                name: {market: strategy_detail(market_rows(rows, market))
                       for market in ("MX", "US")}
                for name, rows in (("BREAKOUT", results), ("REBOUND", rebounds))},
            "bmv_overlay": report.get("bmv_research_overlay") or {},
            "issuer_mapping_verified": False,
            "notes": ["Observed Yahoo research coverage only; not a verified BMV issuer catalogue.",
                      "20% MX is a target, not guaranteed availability.",
                      "Do not automatically approve unverified issuer mappings."]}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args(argv)
    result = audit(json.loads(Path(a.input).read_text(encoding="utf-8")))
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
