"""Generic official-document discovery, bounded and research-only.

Only issuer-configured HTTPS archives and their linked PDF documents are indexed.
A discovered link never proves a document's historical publication date.
No PDF candidate is promoted to a verified observation.
"""
import argparse
import csv
import json
import re
from collections import Counter
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from tradepilot.v6_financial_source_queue_cli import build, read as read_csv
from tradepilot.v6_stop_target_cli import write_csv

COLUMNS=("case_id","symbol","market","signal_date","document_url",
         "document_type","source_archive","discovery_status","period_hint",
         "publication_status","verification_status")
ERROR_COLUMNS=("case_id","symbol","source_archive","error")
PERIOD=re.compile(r"(?<!\d)(?:[1-4]q|q[1-4]|[1-4]t|t[1-4])[-_ ]?20\d{2}|20\d{2}[-_ ]?(?:[1-4]q|q[1-4]|[1-4]t|t[1-4])",re.I)


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=="a":
            href=dict(attrs).get("href")
            if href:
                self.links.append(href)


def trusted_archive_link(archive,link):
    a=urlparse(archive)
    b=urlparse(link)
    host=(a.hostname or "").lower()
    target=(b.hostname or "").lower()
    return (a.scheme=="https" and b.scheme=="https" and bool(host)
            and (target==host or target.endswith("."+host))
            and b.port in (None,443)
            and not b.username and not b.password)


def extract_links(archive,html,max_documents=60):
    parser=AnchorParser()
    parser.feed(html)
    seen=set()
    result=[]
    for href in parser.links:
        url=urljoin(archive,href)
        if not trusted_archive_link(archive,url):
            continue
        if not urlparse(url).path.lower().endswith(".pdf"):
            continue
        if url in seen:
            continue
        seen.add(url)
        result.append(url)
        if len(result)>=max_documents:
            break
    return result


def fetch_html(url,max_bytes=2_000_000):
    req=Request(url,headers={"User-Agent":"TradePilotResearch/1.0 (public issuer archive research)"})
    with urlopen(req,timeout=20) as response:
        final=response.geturl()
        if not trusted_archive_link(url,final):
            raise ValueError("Archive redirected to a different host")
        data=response.read(max_bytes+1)
    if len(data)>max_bytes:
        raise ValueError("Archive HTML exceeds size limit")
    return data.decode("utf-8",errors="replace")


def discover(queue,fetcher=fetch_html,max_documents=60):
    docs,errors=[],[]
    cache={}
    for case in queue:
        if case["market"]!="MX":
            continue
        archive=case.get("official_archive","").strip()
        initial=case.get("initial_document","").strip()
        urls=[]
        if initial and initial.lower().split("?")[0].endswith(".pdf") and urlparse(initial).scheme=="https":
            urls.append((initial,"CURATED_DOCUMENT"))
        if archive:
            try:
                if archive not in cache:
                    cache[archive]=extract_links(archive,fetcher(archive),max_documents)
                urls.extend((url,"ARCHIVE_LINK") for url in cache[archive])
            except Exception as exc:
                errors.append(dict(case_id=case["case_id"],symbol=case["symbol"],
                                   source_archive=archive,error=f"{type(exc).__name__}: {exc}"))
        for url,kind in dict(urls).items():
            hint=PERIOD.search(urlparse(url).path)
            docs.append(dict(case_id=case["case_id"],symbol=case["symbol"],
                market="MX",signal_date=case["signal_date"],document_url=url,
                document_type="PDF",source_archive=archive,
                discovery_status=kind,period_hint=hint.group(0) if hint else "",
                publication_status="UNKNOWN",verification_status="PENDING_REVIEW"))
    return docs,errors


def main(argv=None):
    parser=argparse.ArgumentParser(description="Bounded official PDF link discovery; no inferred dates")
    parser.add_argument("--cases",default=".cache/v6_pilot_cases.csv")
    parser.add_argument("--catalog",default="research/v6_mx_source_catalog.csv")
    parser.add_argument("--prefix",default=".cache/v6_financial_discovery")
    parser.add_argument("--max-documents",type=int,default=60)
    args=parser.parse_args(argv)
    if not 1<=args.max_documents<=200:
        parser.error("--max-documents must be 1..200")
    queue=build(read_csv(args.cases),read_csv(args.catalog))
    docs,errors=discover(queue,max_documents=args.max_documents)
    write_csv(args.prefix+"_documents.csv",docs,COLUMNS)
    write_csv(args.prefix+"_errors.csv",errors,ERROR_COLUMNS)
    p=Path(args.prefix+"_summary.json")
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps({"documents":len(docs),"errors":len(errors),
                             "symbols":dict(Counter(r["symbol"] for r in docs)),
                             "verified":0,"publication_dates_inferred":0,
                             "policy":"Document links are leads only; verify report period and historical availability independently"},
                            indent=2)+"\n",encoding="utf-8")
    print(f"Official discovery: {len(docs)} leads, {len(errors)} errors, 0 verified")


if __name__=="__main__":
    main()
