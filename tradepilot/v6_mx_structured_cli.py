"""Extract structured-looking financial table rows with neighboring headers.

Research-only. Never promotes numbers to VERIFIED or modifies scores.
"""
import argparse
import csv
import json
import re
from pathlib import Path
from datetime import date

from tradepilot.v6_mx_curated_cli import CATALOG, resolve_document
from tradepilot.v6_mx_pdf_research_cli import fetch, trusted_url
from tradepilot.v6_stop_target_cli import write_csv

COLUMNS = ("symbol","report_period","source_url","page","metric","basis",
           "header_context","table_row","numeric_cells","published_at",
           "signal_date","status","note")
ROW_PATTERNS = {
    "revenue": re.compile(r"^ventas netas\b|^net sales\b", re.I),
    "net_income": re.compile(r"^utilidad neta\b|^net income\b", re.I),
    "operating_cash_flow": re.compile(
        r"^(?:flujos? (?:netos? )?de efectivo (?:procedentes|provenientes|de las actividades de operaci[oó]n)|"
        r"efectivo neto (?:generado|utilizado) por actividades de operaci[oó]n|"
        r"net cash (?:provided by|from) operating activities)", re.I),
}
NUMBER = re.compile(r"(?<![A-Za-z])(?:\(?-?\$?\s*\d[\d,]*(?:\.\d+)?\)?%?)")
HEADER = re.compile(r"2T2[23]|3T2[23]|2Q2[23]|3Q2[23]|2022|2023|Pre-IFRS|Post-IFRS|NIIF|millones", re.I)


def table_rows(pdf_data, row, url, max_pages=120):
    import pymupdf
    found = []
    with pymupdf.open(stream=pdf_data, filetype="pdf") as doc:
        for page_index in range(min(len(doc), max_pages)):
            page = doc[page_index]
            lines = [" ".join(x.split()) for x in page.get_text("text", sort=True).splitlines()]
            for index, line in enumerate(lines):
                metric = next((key for key, pattern in ROW_PATTERNS.items()
                               if pattern.search(line)), None)
                if metric is None or len(NUMBER.findall(line)) < 2:
                    continue
                nearby = lines[max(0,index-22):index]
                headers = [x for x in nearby if HEADER.search(x)]
                basis = "MIXED_BASIS_REVIEW_REQUIRED" if ("Pre-IFRS" in " ".join(headers) and
                                                         "Post-IFRS" in " ".join(headers)) else "UNCONFIRMED"
                found.append({
                    "symbol": row["symbol"], "report_period": row["report_period"],
                    "source_url": url, "page": page_index+1, "metric": metric,
                    "basis": basis, "header_context": " | ".join(headers[-8:])[:1000],
                    "table_row": line[:1000],
                    "numeric_cells": " | ".join(NUMBER.findall(line)),
                    "published_at": row["publication_date"], "signal_date": row["signal_date"],
                    "status": "PENDING_TABLE_COLUMN_VERIFICATION",
                    "note": "Numbers are NOT verified: confirm units, exact column alignment, consolidation, accounting basis, and date",
                })
    return found


def analyze(rows, fetcher=fetch, extractor=table_rows):
    found, audit, errors = [], [], []
    for row in rows:
        symbol = row["symbol"]
        try:
            signal = date.fromisoformat(row["signal_date"])
            published = row["publication_date"].strip()
            if not published or not row["publication_evidence"].strip():
                status = "MISSING_PUBLICATION_PROOF"
            elif date.fromisoformat(published) >= signal:
                status = "POST_SIGNAL_EXCLUDED"
            else:
                url, resolution = resolve_document(row, fetcher)
                if not url:
                    status = resolution
                elif not trusted_url(url):
                    status = "UNTRUSTED_DOCUMENT"
                else:
                    data = fetcher(url)
                    if not data.startswith(b"%PDF-"):
                        raise ValueError("Not a PDF")
                    found.extend(extractor(data, row, url))
                    status = "TABLE_ROWS_PENDING_REVIEW"
        except Exception as exc:
            status = "ERROR"
            errors.append(f"{symbol}: {type(exc).__name__}: {exc}")
        audit.append({"symbol":symbol,"report_period":row["report_period"],"status":status})
    return found, audit, errors


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog",default=CATALOG)
    parser.add_argument("--prefix",default=".cache/v6_mx_structured")
    args = parser.parse_args(argv)
    with open(args.catalog,encoding="utf-8-sig",newline="") as f:
        rows = list(csv.DictReader(f))
    found, audit, errors = analyze(rows)
    write_csv(args.prefix+"_rows.csv",found,COLUMNS)
    write_csv(args.prefix+"_audit.csv",audit,("symbol","report_period","status"))
    path = Path(args.prefix+"_errors.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(errors,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"Structured PDF candidates: {len(found)}; errors: {len(errors)}; none VERIFIED")


if __name__=="__main__":
    main()
