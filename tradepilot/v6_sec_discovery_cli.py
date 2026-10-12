"""Discover SEC filings that were public before historical US trading signals.

Discovery only: candidates are NOT automatically marked as verified evidence.
Requires SEC_USER_AGENT environment variable with real application/contact details.
All generated files live directly under .cache.
"""
import argparse
import csv
import json
import os
import time
from datetime import date, datetime, time as clock_time, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

FORMS = {"10-K", "10-Q", "8-K", "20-F", "6-K", "40-F"}
HEADERS = ("case_id", "symbol", "signal_date", "company", "form", "filed_at",
           "accepted_at", "source_url", "publication_precision", "research_status")
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"


def _get_json(url, agent, fetcher=None):
    if fetcher:
        return fetcher(url)
    request = Request(url, headers={"User-Agent": agent, "Accept": "application/json"})
    with urlopen(request, timeout=25) as response:
        return json.load(response)


def resolve_ciks(mapping):
    result = {}
    records = mapping.values() if isinstance(mapping, dict) else mapping
    for entry in records:
        symbol = str(entry.get("ticker", "")).upper().strip()
        if symbol:
            result[symbol] = int(entry["cik_str"])
    return result


def _recent_rows(submissions):
    recent = submissions.get("filings", {}).get("recent", {})
    count = len(recent.get("form", []))
    for index in range(count):
        yield {key: values[index] if index < len(values) else None
               for key, values in recent.items() if isinstance(values, list)}


def _acceptance(raw):
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        # SEC acceptanceDateTime commonly has no offset, expressed in Eastern time.
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("America/New_York"))
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def discover(cases, tickers, fetcher, lookback_days=365):
    from datetime import timedelta
    cik_map = resolve_ciks(tickers)
    result, errors = [], []
    by_symbol = {}
    for row in cases:
        if row["market"] == "US":
            by_symbol.setdefault(row["symbol"].upper(), []).append(row)
    for symbol, relevant in sorted(by_symbol.items()):
        cik = cik_map.get(symbol)
        if cik is None:
            errors.append(f"{symbol}: no SEC CIK match")
            continue
        try:
            submission = fetcher(SEC_SUBMISSIONS.format(cik=cik))
        except Exception as exc:
            errors.append(f"{symbol}: {type(exc).__name__}: {exc}")
            continue
        for case in relevant:
            day = date.fromisoformat(case["signal_date"])
            cutoff = datetime.combine(day, clock_time(16, 0),
                                      tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
            earliest = day - timedelta(days=lookback_days)
            for filing in _recent_rows(submission):
                if filing.get("form") not in FORMS:
                    continue
                try:
                    filed_day = date.fromisoformat(filing.get("filingDate", ""))
                except ValueError:
                    continue
                if not earliest <= filed_day <= day:
                    continue
                accepted = _acceptance(filing.get("acceptanceDateTime"))
                # No acceptance timestamp: conservatively exclude signal-day filings.
                if accepted is not None and accepted > cutoff:
                    continue
                if accepted is None and filed_day >= day:
                    continue
                accession = filing.get("accessionNumber")
                primary = filing.get("primaryDocument")
                if not accession or not primary:
                    continue
                source_url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                              f"{accession.replace('-', '')}/{primary}")
                result.append({
                    "case_id": case["case_id"], "symbol": symbol,
                    "signal_date": case["signal_date"],
                    "company": submission.get("name", ""),
                    "form": filing["form"], "filed_at": str(filed_day),
                    "accepted_at": accepted.isoformat() if accepted else "",
                    "source_url": source_url,
                    "publication_precision": "ACCEPTANCE_TIMESTAMP" if accepted else "FILING_DATE_ONLY",
                    "research_status": "CANDIDATE_NOT_REVIEWED",
                })
    result.sort(key=lambda r: (r["case_id"], r["filed_at"], r["form"]), reverse=False)
    return result, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="Discover historical SEC filings for v6 US cases")
    parser.add_argument("--cases", default=".cache/v6_pilot_cases.csv")
    parser.add_argument("--output", default=".cache/v6_sec_candidates.csv")
    parser.add_argument("--errors", default=".cache/v6_sec_errors.json")
    parser.add_argument("--lookback-days", type=int, default=365)
    args = parser.parse_args(argv)
    agent = os.getenv("SEC_USER_AGENT", "").strip()
    if not agent or "@" not in agent:
        parser.error("Set SEC_USER_AGENT with a real contact email before using SEC data")
    if args.lookback_days < 1:
        parser.error("--lookback-days must be positive")
    with Path(args.cases).open(newline="", encoding="utf-8-sig") as f:
        cases = list(csv.DictReader(f))
    if not cases:
        parser.error("No pilot cases found")
    tickers = _get_json(SEC_TICKERS, agent)
    def fetch(url):
        time.sleep(0.2)  # Moderate SEC requests; no parallel requests.
        return _get_json(url, agent)
    rows, errors = discover(cases, tickers, fetch, args.lookback_days)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    Path(args.errors).write_text(json.dumps(errors, indent=2) + "\n", encoding="utf-8")
    print(f"SEC candidates: {len(rows)}; issues: {len(errors)}")
    print(f"Candidates: {output}")
    print(f"Issues: {args.errors}")
    print("Review filing content manually; discovery does not imply positive or negative evidence.")


if __name__ == "__main__":
    main()
