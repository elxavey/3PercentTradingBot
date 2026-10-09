"""Audit observed Mexico/US coverage without claiming BMV issuer verification."""
import argparse
import json
from collections import Counter
from pathlib import Path


def audit(report):
    results = report.get("results") or []
    mx = [r for r in results if str(r.get("symbol", "")).endswith(".MX")]
    us = [r for r in results if not str(r.get("symbol", "")).endswith(".MX")]
    def detail(rows):
        return {"reviewed": len(rows), "current": sum((r.get("session_quality") or {}).get("state") == "CURRENT" for r in rows),
                "rejected": sum(r.get("state") in ("REJECT", "ERROR") for r in rows),
                "rejection_reasons": dict(Counter(r.get("reason", "UNKNOWN") for r in rows if r.get("state") in ("REJECT", "ERROR")))}
    overlay = report.get("bmv_research_overlay") or {}
    return {"requested": report.get("requested"), "MX": detail(mx), "US": detail(us),
            "mexico_share_pct": round(100*len(mx)/len(results), 2) if results else None,
            "bmv_overlay": overlay,
            "issuer_mapping_verified": False,
            "notes": ["Observed Yahoo research coverage only; not a complete verified BMV issuer catalogue.",
                      "Never treat unverified issuer mapping as approved automatically."]}


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
