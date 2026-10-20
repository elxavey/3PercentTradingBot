"""6.2.1-6.2.2: extract contextual PDF financial table rows for human audit.

Rows are CANDIDATE_ONLY and NEVER written to verified observations.
"""
import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path

from tradepilot.v6_mx_curated_cli import CATALOG, resolve_document
from tradepilot.v6_mx_pdf_research_cli import TERMS, fetch, trusted_url
from tradepilot.v6_stop_target_cli import write_csv

COLUMNS = ("symbol", "report_period", "signal_date", "published_at",
           "publication_evidence", "source_url", "page", "metric",
           "row_text", "previous_row", "next_row", "numeric_tokens",
           "candidate_status", "review_note")
NUMERIC = re.compile(r"(?<![A-Za-z])\\(?!)") if False else re.compile(
    r"(?<![A-Za-z])[-−]?(?:\\d{1,3}(?:[, ]\\d{3})+|\\d+)(?:\\.\\d+)?%?")
# Deliberately preserve text as printed; no numeric interpretation without
# identifying year/quarter columns, consolidation, currency and scaling.


def extract_rows(pdf_data, row, url, max_pages=120):
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required") from exc
    results = []
    with fitz.open(stream=pdf_data, filetype="pdf") as doc:
        for page_no in range(min(len(doc), max_pages)):
            lines = [" ".join(x.split()) for x in doc[page_no].get_text("text", sort=True).splitlines()]
            for index, line in enumerate(lines):
                if not line:
                    continue
                for metric, pattern in TERMS.items():
                    if not pattern.search(line):
                        continue
                    previous = " | ".join(lines[max(0, index - 2):index])
                    following = " | ".join(lines[index + 1:index + 5])
                    tokens = NUMERIC.findall(" ".join((line, following)))
                    results.append({
                        "symbol": row["symbol"], "report_period": row["report_period"],
                        "signal_date": row["signal_date"], "published_at": row["publication_date"],
                        "publication_evidence": row["publication_evidence"],
                        "source_url": url, "page": page_no + 1, "metric": metric,
                        "row_text": line[:600], "previous_row": previous[:600],
                        "next_row": following[:900], "numeric_tokens": " | ".join(tokens[:30]),
                        "candidate_status": "PENDING_REVIEW",
                        "review_note": "Check quarterly columns, consolidated basis, currency, scale, signed values, and original publication date",
                    })
    return results


def research(rows, fetcher=fetch, extractor=extract_rows):
    candidates, audit, errors = [], [], []
    for row in rows:
        symbol = row["symbol"]
        status = "NOT_REVIEWED"
        url = ""
        try:
            signal = date.fromisoformat(row["signal_date"])
            published = row["publication_date"].strip()
            if published and date.fromisoformat(published) >= signal:
                status = "POST_SIGNAL_EXCLUDED"
            else:
                url, resolution = resolve_document(row, fetcher)
                if not url:
                    status = resolution
                elif not trusted_url(url):
                    status = "UNTRUSTED_SOURCE"
                elif not published or not row["publication_evidence"].strip():
                    status = "MISSING_PUBLICATION_PROOF"
                else:
                    raw = fetcher(url)
                    if not raw.startswith(b"%PDF-"):
                        raise ValueError("Not a PDF")
                    candidates.extend(extractor(raw, row, url))
                    status = "CANDIDATES_PENDING_REVIEW"
        except Exception as exc:
            status = "ERROR"
            errors.append(f"{symbol}: {type(exc).__name__}: {exc}")
        audit.append({"symbol": symbol, "report_period": row["report_period"],
                      "document_url": url or row["document_url"], "status": status})
    return candidates, audit, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="Extract contextual financial PDF rows; review-only")
    parser.add_argument("--catalog", default=CATALOG)
    parser.add_argument("--prefix", default=".cache/v6_mx_table_review")
    args = parser.parse_args(argv)
    with Path(args.catalog).open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    candidates, audit, errors = research(rows)
    write_csv(args.prefix + "_candidates.csv", candidates, COLUMNS)
    write_csv(args.prefix + "_audit.csv", audit,
              ("symbol", "report_period", "document_url", "status"))
    p = Path(args.prefix + "_errors.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(errors, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Financial table review: {len(candidates)} contextual rows, {len(errors)} errors")
    print("No verified observations written; scores remain unchanged.")


if __name__ == "__main__":
    main()
