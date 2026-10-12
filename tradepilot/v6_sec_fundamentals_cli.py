"""TradePilot v6: point-in-time SEC XBRL fundamentals, research only.

Fetches SEC companyfacts for US pilot cases. Uses only facts filed BEFORE signal
date (conservative date-only cutoff). Reports candidates, not investment advice.
"""
import argparse
import csv
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

METRICS = {
    "revenue": ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "SalesRevenueNet"),
    "net_income": ("NetIncomeLoss",),
    "assets": ("Assets",),
    "liabilities": ("Liabilities",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue",),
    "long_term_debt": ("LongTermDebtCurrent", "LongTermDebtNoncurrent", "LongTermDebt"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
}
COLUMNS = ("case_id", "symbol", "signal_date", "metric", "value", "unit",
           "period_start", "period_end", "filed", "form", "accession",
           "source_url", "status")
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"


def fetch_json(url, agent):
    req = Request(url, headers={"User-Agent": agent, "Accept": "application/json"})
    with urlopen(req, timeout=30) as response:
        return json.load(response)


def cik_mapping(payload):
    entries = payload.values() if isinstance(payload, dict) else payload
    return {str(entry["ticker"]).upper(): int(entry["cik_str"]) for entry in entries}


def select_fact(companyfacts, metric, signal_date):
    """Select most recently ended valid filed fact, excluding signal day itself.

    Filing date alone cannot establish intraday availability. Use strict prior-day
    cutoff; for flow metrics prefer 60-120 day periods; instant metrics have no start.
    """
    day = date.fromisoformat(signal_date)
    candidates = []
    for priority, tag in enumerate(METRICS[metric]):
        fact = companyfacts.get("facts", {}).get("us-gaap", {}).get(tag, {})
        for unit, observations in fact.get("units", {}).items():
            if unit not in ("USD",):
                continue
            for item in observations:
                if item.get("form") not in ("10-K", "10-Q", "20-F", "6-K"):
                    continue
                try:
                    filed = date.fromisoformat(item["filed"])
                    ended = date.fromisoformat(item["end"])
                    started = date.fromisoformat(item["start"]) if item.get("start") else None
                except (ValueError, KeyError, TypeError):
                    continue
                if filed >= day or ended > filed or ended > day:
                    continue
                if metric in ("revenue", "net_income", "operating_cash_flow"):
                    if started is None or not 60 <= (ended - started).days <= 120:
                        continue
                elif started is not None:
                    continue
                if not isinstance(item.get("val"), (int, float)):
                    continue
                candidates.append((ended, filed, -priority, item, unit))
    if not candidates:
        return None
    _, _, _, selected, unit = max(candidates, key=lambda x: (x[0], x[1], x[2]))
    accession = selected.get("accn", "")
    cik = int(companyfacts["cik"])
    return {
        "value": selected["val"], "unit": unit,
        "period_start": selected.get("start", ""),
        "period_end": selected["end"], "filed": selected["filed"],
        "form": selected["form"], "accession": accession,
        "source_url": (f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                       f"{accession.replace('-', '')}/") if accession else "",
        "status": "CANDIDATE_FILED_BEFORE_SIGNAL",
    }


def analyze(cases, mapping, fetcher):
    rows, errors = [], []
    for case in cases:
        if case.get("market") != "US":
            continue
        symbol = case["symbol"].upper()
        cik = mapping.get(symbol)
        if cik is None:
            errors.append(f"{symbol}: SEC CIK not found")
            continue
        try:
            facts = fetcher(SEC_FACTS.format(cik=cik))
        except Exception as exc:
            errors.append(f"{symbol}: {type(exc).__name__}: {exc}")
            continue
        for metric in METRICS:
            fact = select_fact(facts, metric, case["signal_date"])
            if fact:
                rows.append({"case_id": case["case_id"], "symbol": symbol,
                             "signal_date": case["signal_date"], "metric": metric, **fact})
    return rows, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="SEC point-in-time fundamental candidate extraction")
    parser.add_argument("--cases", default=".cache/v6_pilot_cases.csv")
    parser.add_argument("--output", default=".cache/v6_sec_fundamentals.csv")
    parser.add_argument("--errors", default=".cache/v6_sec_fundamentals_errors.json")
    args = parser.parse_args(argv)
    agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if "@" not in agent:
        parser.error("SEC_USER_AGENT must include a real contact email")
    with Path(args.cases).open(newline="", encoding="utf-8-sig") as stream:
        cases = list(csv.DictReader(stream))
    mapping = cik_mapping(fetch_json(SEC_TICKERS, agent))
    def polite_fetch(url):
        time.sleep(0.2)
        return fetch_json(url, agent)
    rows, errors = analyze(cases, mapping, polite_fetch)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    Path(args.errors).write_text(json.dumps(errors, indent=2) + "\n", encoding="utf-8")
    print(f"Fundamental candidates: {len(rows)}; errors: {len(errors)}")
    print(f"Saved: {path}")
    print("No scoring or automatic trading decisions; review financial contexts first.")


if __name__ == "__main__":
    main()
