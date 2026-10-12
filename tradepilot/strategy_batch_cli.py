"""Select a reproducible, balanced historical research batch from an existing radar JSON."""
from __future__ import annotations
import argparse
import json
from collections import Counter
from pathlib import Path


def select_symbols(report, mx_limit=60, us_limit=140):
    """Include liquid/interesting symbols first, then diversify deterministically."""
    results = report.get("results") or []
    if not results:
        raise ValueError("Radar JSON has no results")
    selected = []
    counts = {}
    for market, limit in (("MX", mx_limit), ("US", us_limit)):
        rows = [r for r in results if bool(str(r.get("symbol", "")).upper().endswith(".MX")) == (market == "MX")]
        eligible = [r for r in rows if r.get("state") not in ("ERROR", "REJECT")
                    and isinstance(r.get("symbol"), str) and r["symbol"].strip()]
        rank = {"CONFIRMED_RESEARCH": 0, "BREAKOUT_PENDING_CONFIRMATION": 1,
                "APPROACHING": 2, "MONITORING": 3}
        eligible.sort(key=lambda r: (rank.get(r.get("state"), 4),
                                     -(r.get("quality_score") or 0), r["symbol"]))
        names = list(dict.fromkeys(r["symbol"].strip().upper() for r in eligible))
        selected.extend(names[:limit])
        counts[market] = {"available": len(rows), "eligible": len(names),
                          "selected": min(len(names), limit),
                          "requested": limit}
    return {"symbols": selected, "coverage": counts,
            "selection": "RADAR_STATES_HEURISTIC_NOT_OUT_OF_SAMPLE",
            "limitations": ["SELECTION_BIAS_TOWARD_RADAR_STATES", "BMV_MAPPING_NOT_VERIFIED"]}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", default=".cache/strategy_symbols_200.txt")
    p.add_argument("--metadata", default=".cache/strategy_symbols_200_metadata.json")
    p.add_argument("--mx-limit", type=int, default=60)
    p.add_argument("--us-limit", type=int, default=140)
    a = p.parse_args(argv)
    if not 0 <= a.mx_limit <= 1000 or not 0 <= a.us_limit <= 1000 or a.mx_limit+a.us_limit < 1:
        p.error("Invalid market limits")
    report = json.loads(Path(a.input).read_text(encoding="utf-8"))
    result = select_symbols(report, mx_limit=a.mx_limit, us_limit=a.us_limit)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(result["symbols"])+"\n", encoding="utf-8")
    meta = Path(a.metadata)
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps({k:v for k,v in result.items() if k!="symbols"},indent=2),encoding="utf-8")
    print(json.dumps({"count":len(result["symbols"]),"coverage":result["coverage"],
                      "symbols_file":str(out),"metadata":str(meta)},indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
