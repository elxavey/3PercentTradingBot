"""Discover and extract auditable PDF *candidates* from official Mexican issuer sites.

No OCR, no automatic numerical verification, no publication-date inference.
PDF text lines are research leads, never financial observations.
"""
import argparse
import csv
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

CATALOG = "research/v6_mx_source_catalog.csv"
COLUMNS = ("symbol", "source_url", "page", "matched_metric", "text_excerpt",
           "verification_status", "note")
TERMS = {
    "revenue": re.compile(r"ventas netas|ingresos totales|ingresos netos|net sales|revenue", re.I),
    "net_income": re.compile(r"utilidad neta|resultado neto|net income|net profit", re.I),
    "operating_cash_flow": re.compile(r"flujos? de efectivo (?:netos? )?(?:de|por|proveniente)|cash flows? from operating", re.I),
}
ALLOWED_HOSTS = {
    "alsea.net", "alsea.mx", "grupoalsea.com.mx",
    "alpek.com", "grupobimbo.com", "grupobimbo.com.mx",
    "elpuertodeliverpool.mx", "liverpool.com.mx", "chedraui.com.mx",
    "pinfra.com.mx", "bmv.com.mx",
}


def trusted_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host == d or host.endswith("." + d) for d in ALLOWED_HOSTS)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def discover_pdf_links(html, base_url):
    parser = Links()
    parser.feed(html)
    urls = [urljoin(base_url, link) for link in parser.hrefs]
    return sorted({u for u in urls if trusted_url(u) and
                   urlparse(u).path.lower().endswith(".pdf")})


def pdf_candidates(pdf_bytes, symbol, url, max_pages=80):
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required: pip install pymupdf") from exc
    rows = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        for page_index in range(min(len(document), max_pages)):
            lines = document[page_index].get_text("text").splitlines()
            for line in lines:
                clean = " ".join(line.split())
                if len(clean) < 7:
                    continue
                for metric, regex in TERMS.items():
                    if regex.search(clean):
                        rows.append({
                            "symbol": symbol, "source_url": url,
                            "page": page_index + 1, "matched_metric": metric,
                            "text_excerpt": clean[:300],
                            "verification_status": "PENDING_REVIEW",
                            "note": "Confirm exact row, quarter, units, consolidation and published date in original PDF",
                        })
    return rows


def fetch(url, max_bytes=25_000_000):
    if not trusted_url(url):
        raise ValueError(f"Untrusted source host: {url}")
    req = Request(url, headers={"User-Agent": "TradePilotResearch/1.0 (manual source verification)"})
    with urlopen(req, timeout=30) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Source exceeds 25 MB limit")
    return data


def run(catalog, download=fetch):
    candidates, errors, discovered = [], [], []
    for item in catalog:
        symbol = item["symbol"]
        urls = []
        initial = item.get("initial_document", "").strip()
        if initial:
            urls.append(initial)
        archive = item.get("official_archive", "").strip()
        if archive:
            try:
                html = download(archive).decode("utf-8", errors="replace")
                found = discover_pdf_links(html, archive)
                discovered.extend({"symbol": symbol, "url": url} for url in found)
            except Exception as exc:
                errors.append(f"{symbol}: archive discovery: {type(exc).__name__}: {exc}")
        # Only explicitly curated documents are downloaded, to avoid pulling hundreds
        # of unrelated or post-signal PDFs from historical archive pages.
        for url in urls:
            try:
                data = download(url)
                if not data.startswith(b"%PDF-"):
                    raise ValueError("Document is not a PDF")
                candidates.extend(pdf_candidates(data, symbol, url))
            except Exception as exc:
                errors.append(f"{symbol}: {url}: {type(exc).__name__}: {exc}")
    return candidates, discovered, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="Locate Mexican issuer PDFs and extract page-level research leads")
    parser.add_argument("--catalog", default=CATALOG)
    parser.add_argument("--output", default=".cache/v6_mx_pdf_candidates.csv")
    parser.add_argument("--discovered", default=".cache/v6_mx_discovered_pdfs.csv")
    parser.add_argument("--errors", default=".cache/v6_mx_pdf_errors.json")
    args = parser.parse_args(argv)
    with Path(args.catalog).open(newline="", encoding="utf-8-sig") as stream:
        catalog = list(csv.DictReader(stream))
    rows, discovered, errors = run(catalog)
    for filename, data, fields in (
        (args.output, rows, COLUMNS),
        (args.discovered, discovered, ("symbol", "url")),
    ):
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(data)
    Path(args.errors).write_text(json.dumps(errors, indent=2) + "\n", encoding="utf-8")
    print(f"PDF leads: {len(rows)}; discovered official PDFs: {len(discovered)}; errors: {len(errors)}")
    print("Candidates are NOT verified financial values. Review original pages and publication dates.")


if __name__ == "__main__":
    main()
