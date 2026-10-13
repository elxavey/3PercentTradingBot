"""Bounded five-issuer official-PDF research pass; never auto-certifies numbers.

Discover source links, filter by quarter/year, inspect PDF page snippets, then
run the existing verified-only batch. Downloaded documents are research leads.
"""
import argparse
import csv
import json
import re
from pathlib import Path
from urllib.parse import urlparse, urljoin
from html.parser import HTMLParser

from tradepilot.v6_mx_pdf_research_cli import (
    discover_pdf_links, fetch, pdf_candidates, trusted_url, COLUMNS,
)
from tradepilot.v6_mx_batch_cli import SYMBOLS, read_csv, main as batch_main
from tradepilot.v6_stop_target_cli import write_csv

ARCHIVES = {
    "ALSEA.MX": "https://www.alsea.net/inversionistas/2023.html",
    "BIMBOA.MX": "https://www.grupobimbo.com/en/investors/reports/quarterly-reports/quarterly-reports-2023",
    "LIVEPOLC-1.MX": "https://www.elpuertodeliverpool.mx/",
    "CHDRAUIB.MX": "https://www.chedraui.com.mx/",
    "PINFRA.MX": "https://www.pinfra.com.mx/reporte-trimestral",
}
PERIODS = {
    "ALSEA.MX": ("2t23", "2q23", "2t2023", "2q2023", "2023_2", "2023-2"),
    "BIMBOA.MX": ("3q23", "3t23", "3q2023", "3t2023", "2023_3", "2023-3"),
    "LIVEPOLC-1.MX": ("3t22", "3q22", "3t2022", "3q2022", "2022_3", "2022-3"),
    "CHDRAUIB.MX": ("3t23", "3q23", "3t2023", "3q2023", "2023_3", "2023-3"),
    "PINFRA.MX": ("3t22", "3q22", "3t2022", "3q2022", "2022_3", "2022-3"),
}
DISCOVERY_COLUMNS = ("symbol", "url", "period_match", "status", "note")


def targeted_links(symbol, urls, limit=4):
    """Never download an arbitrary issuer archive's entire historical PDF set."""
    patterns = PERIODS[symbol]
    matched = [u for u in urls if any(p in urlparse(u).path.lower() for p in patterns)]
    return matched[:limit]


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def crawl_pdfs(symbol, start_url, fetcher, max_pages=12):
    """Bounded issuer-only archive crawl; never follows off-domain HTML links."""
    origin = urlparse(start_url).hostname
    queue = [(start_url, 0)]
    visited, pdfs, failures = set(), set(), []
    hints = ("invest", "report", "informe", "trimestr", "quarter",
             "financ", "resultado", "2022", "2023", "histor", "archivo")
    while queue and len(visited) < max_pages:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            if urlparse(url).path.lower().endswith((".mp4", ".mov", ".zip", ".xlsx", ".jpg", ".png")):
                continue
            html = fetcher(url).decode("utf-8", errors="replace")
            parser = PageLinks()
            parser.feed(html)
            for href in parser.hrefs:
                link = urljoin(url, href)
                parsed = urlparse(link)
                if not trusted_url(link):
                    continue
                if parsed.path.lower().endswith(".pdf"):
                    pdfs.add(link)
                elif (depth < 2 and parsed.hostname == origin and
                      any(h in (parsed.path + "?" + parsed.query).lower() for h in hints)
                      and not parsed.path.lower().endswith((".mp4", ".mov", ".zip", ".xlsx", ".jpg", ".png"))
                      and link not in visited and len(queue) < 60):
                    queue.append((link, depth + 1))
        except Exception as exc:
            failures.append(f"{symbol}: {url}: {type(exc).__name__}: {exc}")
    return sorted(pdfs), failures


def research(fetcher=fetch, pdf_reader=pdf_candidates, max_pdfs=4):
    leads, discovered, errors = [], [], []
    for symbol in SYMBOLS:
        archive = ARCHIVES[symbol]
        links, crawl_errors = crawl_pdfs(symbol, archive, fetcher)
        errors.extend(crawl_errors)
        selected = targeted_links(symbol, links, max_pdfs)
        for url in links:
            discovered.append({
                "symbol": symbol, "url": url,
                "period_match": "YES" if url in selected else "NO",
                "status": "DISCOVERED_ONLY",
                "note": "PDF URL is a lead, not publication-date or metric verification",
            })
        if not selected:
            errors.append(f"{symbol}: no official PDF URL matched quarter after bounded crawl; manual review required")
        for url in selected:
            try:
                data = fetcher(url)
                if not data.startswith(b"%PDF-"):
                    raise ValueError("not a PDF")
                leads.extend(pdf_reader(data, symbol, url))
            except Exception as exc:
                errors.append(f"{symbol}: {url}: {type(exc).__name__}: {exc}")
    return leads, discovered, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="Research official MX issuer PDFs and run five-issuer verified-only batch")
    parser.add_argument("--max-pdfs-per-issuer", type=int, default=4)
    parser.add_argument("--prefix", default=".cache/v6_mx_research")
    args = parser.parse_args(argv)
    if not 1 <= args.max_pdfs_per_issuer <= 8:
        parser.error("--max-pdfs-per-issuer must be 1..8")
    leads, discovered, errors = research(max_pdfs=args.max_pdfs_per_issuer)
    write_csv(args.prefix + "_candidates.csv", leads, COLUMNS)
    write_csv(args.prefix + "_discovered.csv", discovered, DISCOVERY_COLUMNS)
    path = Path(args.prefix + "_errors.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(errors, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"MX research: {len(discovered)} PDF links, {len(leads)} text leads, {len(errors)} warnings")
    print("Research leads are NOT VERIFIED; no source numbers are auto-promoted.")
    batch_main([])


if __name__ == "__main__":
    main()
