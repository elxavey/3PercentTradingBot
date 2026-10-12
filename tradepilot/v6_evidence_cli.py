"""Validate point-in-time financial evidence for TradePilot v6.

No network calls, fabricated evidence, or trading scores. Research is entered
in evidence_template.json and checked before it is used for analysis.
"""
import argparse
import csv
import json
from collections import Counter
from datetime import date, datetime, time, timezone
from pathlib import Path
from urllib.parse import urlparse

CATEGORIES = {"EARNINGS", "DIVIDEND", "M_AND_A", "GUIDANCE", "DEBT", "REGULATORY", "OTHER"}
ASSESSMENTS = {"FAVORABLE", "RISK", "NEUTRAL", "UNCERTAIN"}
STATUSES = {"NOT_RESEARCHED", "IN_PROGRESS", "REVIEWED"}
COLUMNS = ("case_id", "symbol", "market", "strategy", "signal_date", "fixed_outcome",
           "review_status", "usable_evidence", "excluded_evidence", "risk_facts",
           "favorable_facts", "neutral_facts", "uncertain_facts", "issues")


def _timestamp(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing publication timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("publication timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def validate_evidence(item, signal_date, cutoff=None):
    """Return (usable, reason). Same-day evidence needs an explicit close cutoff."""
    if not isinstance(item, dict):
        return False, "evidence is not an object"
    if item.get("category") not in CATEGORIES:
        return False, "invalid category"
    if item.get("assessment") not in ASSESSMENTS:
        return False, "invalid assessment"
    if not isinstance(item.get("headline"), str) or not item["headline"].strip():
        return False, "missing headline"
    url = item.get("source_url")
    if not isinstance(url, str) or urlparse(url).scheme != "https" or not urlparse(url).netloc:
        return False, "source_url must be an HTTPS URL"
    if item.get("available_by_signal_close") is not True:
        return False, "availability not explicitly verified"
    try:
        published = _timestamp(item.get("published_at"))
        day = date.fromisoformat(signal_date)
        if cutoff is not None:
            closing = _timestamp(cutoff)
            if published > closing:
                return False, "published after signal cutoff"
        else:
            # With no verified exchange closing timestamp, exclude all same-day
            # releases even if they appear earlier in UTC.
            if published.date() >= day:
                return False, "same-day or later publication needs signal_close_at"
        return True, "OK"
    except (ValueError, TypeError, OverflowError) as exc:
        return False, str(exc)


def consolidate(cases_csv, evidence_json):
    with Path(cases_csv).open(newline="", encoding="utf-8-sig") as stream:
        cases = list(csv.DictReader(stream))
    if not cases or any(not r.get("case_id") for r in cases):
        raise ValueError("Pilot CSV is empty or has missing case_id")
    ids = [r["case_id"] for r in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case_id in pilot CSV")
    document = json.loads(Path(evidence_json).read_text(encoding="utf-8-sig"))
    if document.get("schema_version") != 1 or not isinstance(document.get("cases"), list):
        raise ValueError("Unsupported evidence document schema")
    evidence_cases = document["cases"]
    evidence_ids = [r.get("case_id") for r in evidence_cases]
    if len(evidence_ids) != len(set(evidence_ids)) or set(evidence_ids) != set(ids):
        raise ValueError("Evidence case IDs must match the pilot exactly")
    by_id = {r["case_id"]: r for r in evidence_cases}
    output = []
    for row in cases:
        source = by_id[row["case_id"]]
        if source.get("symbol") != row["symbol"] or source.get("signal_date") != row["signal_date"]:
            raise ValueError(f"Case identity mismatch: {row['case_id']}")
        status = source.get("review_status", "NOT_RESEARCHED")
        if status not in STATUSES:
            raise ValueError(f"Invalid review status for {row['case_id']}")
        items = source.get("evidence")
        if not isinstance(items, list):
            raise ValueError(f"Evidence must be a list for {row['case_id']}")
        cutoff = source.get("signal_close_at")
        if cutoff is not None:
            close = _timestamp(cutoff)
            # Prevent a timestamp accidentally set on the wrong calendar day.
            if close.date() < date.fromisoformat(row["signal_date"]) - __import__("datetime").timedelta(days=1) or close.date() > date.fromisoformat(row["signal_date"]) + __import__("datetime").timedelta(days=1):
                raise ValueError(f"Implausible signal_close_at for {row['case_id']}")
        counts = Counter()
        issues = []
        for i, item in enumerate(items, 1):
            ok, reason = validate_evidence(item, row["signal_date"], cutoff)
            if ok:
                counts[item["assessment"]] += 1
            else:
                issues.append(f"#{i}: {reason}")
        if status == "REVIEWED" and not items:
            issues.append("reviewed without evidence; explicitly document no-findings in research_notes")
        output.append({
            "case_id": row["case_id"], "symbol": row["symbol"],
            "market": row["market"], "strategy": row["strategy"],
            "signal_date": row["signal_date"], "fixed_outcome": row["fixed_outcome"],
            "review_status": status, "usable_evidence": sum(counts.values()),
            "excluded_evidence": len(items) - sum(counts.values()),
            "risk_facts": counts["RISK"], "favorable_facts": counts["FAVORABLE"],
            "neutral_facts": counts["NEUTRAL"], "uncertain_facts": counts["UNCERTAIN"],
            "issues": " | ".join(issues),
        })
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate historical financial evidence without look-ahead")
    parser.add_argument("--cases", default=".cache/v6_pilot/pilot_cases.csv")
    parser.add_argument("--evidence", default=".cache/v6_pilot/evidence_template.json")
    parser.add_argument("--output", default=".cache/v6_pilot/evidence_review.csv")
    args = parser.parse_args(argv)
    rows = consolidate(args.cases, args.evidence)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Cases: {len(rows)}; researched: {sum(r['review_status'] != 'NOT_RESEARCHED' for r in rows)}")
    print(f"Usable evidence: {sum(r['usable_evidence'] for r in rows)}; "
          f"excluded: {sum(r['excluded_evidence'] for r in rows)}")
    print(f"Review: {target}")
    print("No financial score calculated: evidence must be researched and validated first.")


if __name__ == "__main__":
    main()
