"""Cross-check manually reviewed BMV candidates against existing Yahoo radar results.

Never promotes an issuer mapping to verified. Does not fetch network data.
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def review_candidates(rows, radar):
    lookup = {str(r.get("symbol", "")).upper(): r for r in radar.get("results", [])}
    items = []
    for candidate in rows:
        symbol = str(candidate.get("symbol", "")).strip().upper()
        if not symbol.endswith(".MX"):
            continue
        observed = lookup.get(symbol)
        reasons = []
        if candidate.get("quote_type", "").upper() != "EQUITY":
            reasons.append("NOT_EQUITY")
        if candidate.get("mapping_status") != "SERIES_AND_ISSUER_REVIEW":
            reasons.append("MAPPING_REQUIRES_MANUAL_REVIEW")
        if candidate.get("history_status") != "ENOUGH_BARS":
            reasons.append("HISTORY_NOT_CONFIRMED")
        if observed is None:
            reasons.append("NOT_IN_RADAR")
        elif observed.get("state") in ("REJECT", "ERROR"):
            reasons.append("RADAR_" + str(observed.get("reason", "REJECT")))
        items.append({"symbol": symbol, "review_status": "MANUAL_VERIFICATION_REQUIRED",
                      "radar_state": observed.get("state") if observed else None,
                      "research_observations": reasons})
    return {"candidate_count": len(items), "in_radar": sum(i["radar_state"] is not None for i in items),
            "reasons": dict(Counter(reason for i in items for reason in i["research_observations"])),
            "candidates": items, "mapping_verified": False,
            "warning": "No automated issuer/series verification. No automatic addition to production universe."}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--bmv-file", default=".cache/mx_bmv_candidate_validation.csv")
    p.add_argument("--radar", default=".cache/morning_dual_radar_1000.json")
    p.add_argument("--output", default=".cache/bmv_crosscheck_v3.json")
    a = p.parse_args(argv)
    with Path(a.bmv_file).open(encoding="utf-8-sig", newline="") as fh:
        candidates = list(csv.DictReader(fh))
    radar = json.loads(Path(a.radar).read_text(encoding="utf-8"))
    result = review_candidates(candidates, radar)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="candidates"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
