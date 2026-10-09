"""Find Yahoo MX symbol candidates for BMV issuers not matched by the screener.

Results are *suggestions*, not verified issuer/share-series mappings.
Runs locally, rate-limited, with durable per-issuer checkpointing.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

DEFAULT_INPUT = Path(".cache/mx_bmv_issuer_mapping_review.csv")
DEFAULT_OUTPUT = Path(".cache/mx_bmv_search_candidates.csv")
DEFAULT_CHECKPOINT = Path(".cache/mx_bmv_search_checkpoint.json")


def load_checkpoint(path):
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (ValueError, OSError):
        return {}


def save_checkpoint(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def search_issuer(key, name):
    """Search Yahoo by issuer key and name; retain only .MX symbol suggestions."""
    found = {}
    for query in (key, name):
        if not query:
            continue
        result = yf.Search(query, max_results=20, news_count=0)
        for item in result.quotes or []:
            symbol = str(item.get("symbol", "")).upper()
            if not symbol.endswith(".MX"):
                continue
            found.setdefault(symbol, {
                "symbol": symbol,
                "quote_type": str(item.get("quoteType", "")),
                "short_name": str(item.get("shortname", item.get("longname", ""))),
                "matched_by": [],
            })
            found[symbol]["matched_by"].append("KEY" if query == key else "NAME")
    return sorted(found.values(), key=lambda row: (
        not row["symbol"].startswith(key), row["symbol"]))


def main(argv=None):
    p = argparse.ArgumentParser(description="Search unmatched BMV issuers in Yahoo (research only)")
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    p.add_argument("--delay", type=float, default=1.5)
    p.add_argument("--max-issuers", type=int, default=100)
    args = p.parse_args(argv)
    if not 0.5 <= args.delay <= 30 or not 1 <= args.max_issuers <= 500:
        p.error("delay must be 0.5..30; max-issuers 1..500")
    with args.input.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    pending = [row for row in rows if not row.get("yahoo_candidate_symbols", "").strip()]
    checkpoint = load_checkpoint(args.checkpoint)
    processed = 0
    for row in pending:
        key = row["clave_emisora"].strip().upper()
        if key in checkpoint:
            continue
        if processed >= args.max_issuers:
            break
        try:
            matches = search_issuer(key, row["razon_social"].strip())
            checkpoint[key] = {"status": "SEARCHED", "matches": matches,
                               "issuer_name": row["razon_social"]}
        except Exception as exc:
            # Do not persist failures as final: reruns should retry them.
            print(f"{key}: ERROR {type(exc).__name__}: {str(exc)[:100]}", flush=True)
            time.sleep(args.delay)
            continue
        save_checkpoint(args.checkpoint, checkpoint)
        processed += 1
        print(f"[{processed}] {key}: {len(matches)} candidate(s)", flush=True)
        time.sleep(args.delay)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["clave_emisora", "razon_social", "status",
            "yahoo_candidate", "yahoo_quote_type", "yahoo_name", "search_basis",
            "mapping_verified"])
        writer.writeheader()
        for row in pending:
            key = row["clave_emisora"].strip().upper()
            item = checkpoint.get(key, {})
            matches = item.get("matches", [])
            for match in matches or [{}]:
                writer.writerow({
                    "clave_emisora": key, "razon_social": row["razon_social"],
                    "status": item.get("status", "NOT_SEARCHED"),
                    "yahoo_candidate": match.get("symbol", ""),
                    "yahoo_quote_type": match.get("quote_type", ""),
                    "yahoo_name": match.get("short_name", ""),
                    "search_basis": "|".join(match.get("matched_by", [])),
                    "mapping_verified": False,
                })
    found = sum(bool(checkpoint.get(row["clave_emisora"].strip().upper(), {}).get("matches"))
                for row in pending)
    print(f"Unmatched BMV issuers={len(pending)} | with Yahoo search candidates={found} "
          f"| completed searches={sum(row['clave_emisora'].strip().upper() in checkpoint for row in pending)}")
    print(f"Saved {args.output} | checkpoint {args.checkpoint}")
    print("All candidates require manual share-series and instrument-type validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
