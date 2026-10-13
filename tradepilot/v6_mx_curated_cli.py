"""Curated issuer-document audit and PDF candidate extraction; never auto-verifies metrics."""
import argparse
import csv
import json
from datetime import date
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from tradepilot.v6_mx_pdf_research_cli import trusted_url, fetch, pdf_candidates, COLUMNS
from tradepilot.v6_stop_target_cli import write_csv
from tradepilot.v6_mx_batch_cli import SYMBOLS

CATALOG = "research/v6_mx_official_documents.csv"
AUDIT_COLUMNS = ("symbol", "report_period", "document_url", "landing_url",
                 "status", "publication_date", "publication_evidence", "note")


class PDFLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        data = dict(attrs)
        if data.get("href"):
            self.links.append((data["href"], " ".join(str(v) for _, v in attrs)))


def resolve_document(row, fetcher):
    direct = row["document_url"].strip()
    if direct:
        return direct, "CURATED_DIRECT"
    landing = row["landing_url"].strip()
    if not landing:
        return "", "MISSING_SOURCE"
    if not trusted_url(landing):
        raise ValueError("Untrusted landing page")
    page = fetcher(landing).decode("utf-8", errors="replace")
    parser = PDFLinks()
    parser.feed(page)
    candidates = []
    for href, context in parser.links:
        url = urljoin(landing, href)
        if not trusted_url(url) or not urlparse(url).path.lower().endswith(".pdf"):
            continue
        score = sum(word in context.lower() for word in
                    ("results report", "results bmv", "quarterly", "trimestral", "resultados"))
        candidates.append((score, url))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    if not candidates:
        return "", "NO_DIRECT_PDF_ON_LANDING"
    # Do not select an arbitrary PDF when multiple possibilities exist.
    best_score = candidates[0][0]
    best = sorted(set(url for score, url in candidates if score == best_score))
    if best_score == 0 or len(best) != 1:
        return "", "AMBIGUOUS_DOCUMENT_LINK"
    return best[0], "RESOLVED_FROM_LANDING"


def audit(rows, fetcher=fetch, reader=pdf_candidates):
    documents, leads, errors = [], [], []
    for row in rows:
        symbol = row["symbol"].strip()
        signal = date.fromisoformat(row["signal_date"])
        if symbol not in SYMBOLS:
            errors.append(f"{symbol}: not one of the five pilot symbols")
            continue
        published = row["publication_date"].strip()
        status = row["review_status"].strip()
        try:
            url, resolution = resolve_document(row, fetcher)
            note = row["notes"].strip()
            if published and date.fromisoformat(published) >= signal:
                resolution = "POST_SIGNAL_EXCLUDED"
            if not url:
                documents.append(dict(symbol=symbol, report_period=row["report_period"],
                                      document_url="", landing_url=row["landing_url"],
                                      status=resolution, publication_date=published,
                                      publication_evidence=row["publication_evidence"], note=note))
                continue
            if not trusted_url(url):
                raise ValueError("Untrusted document host")
            # Unknown dates can be researched but cannot be accepted as PIT evidence.
            if resolution == "POST_SIGNAL_EXCLUDED":
                documents.append(dict(symbol=symbol, report_period=row["report_period"],
                                      document_url=url, landing_url=row["landing_url"],
                                      status=resolution, publication_date=published,
                                      publication_evidence=row["publication_evidence"], note=note))
                continue
            raw = fetcher(url)
            if not raw.startswith(b"%PDF-"):
                raise ValueError("Not a PDF")
            leads.extend(reader(raw, symbol, url))
            documents.append(dict(symbol=symbol, report_period=row["report_period"],
                                  document_url=url, landing_url=row["landing_url"],
                                  status="TEXT_EXTRACTED_PENDING_VERIFICATION",
                                  publication_date=published,
                                  publication_evidence=row["publication_evidence"], note=note))
        except Exception as exc:
            errors.append(f"{symbol}: {type(exc).__name__}: {exc}")
            documents.append(dict(symbol=symbol, report_period=row["report_period"],
                                  document_url=row["document_url"], landing_url=row["landing_url"],
                                  status="ERROR", publication_date=published,
                                  publication_evidence=row["publication_evidence"],
                                  note=str(exc)))
    return documents, leads, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit curated Mexico issuer quarterly documents")
    parser.add_argument("--catalog", default=CATALOG)
    parser.add_argument("--prefix", default=".cache/v6_mx_curated")
    args = parser.parse_args(argv)
    with Path(args.catalog).open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    documents, leads, errors = audit(rows)
    write_csv(args.prefix + "_documents.csv", documents, AUDIT_COLUMNS)
    write_csv(args.prefix + "_candidates.csv", leads, COLUMNS)
    p = Path(args.prefix + "_errors.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(errors, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Curated MX: {len(documents)} sources, {len(leads)} PDF text leads, {len(errors)} errors")
    print("No automatic VERIFIED observations. No score is changed by this research pass.")


if __name__ == "__main__":
    main()
