"""Mexico equity catalogue builder: verified-source import + Yahoo discovery.

An exchange issuer key is NOT a Yahoo ticker. Never guess share-series mappings.
No trading, no EODHD. Output is a reviewable candidate catalogue.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config import MEXICO_TICKERS, BREAKOUT_TEST_SYMBOLS
from universe_discovery import _discover_region

TICKER = re.compile(r"^[A-Z0-9&+._-]+\\.MX$")
EXCLUDE_MARKERS = ("ETF", "FIBRA", "FIBR", "TRAC", "ISHRS", "FONDO", "CKD", "CERPI")
SYMBOL_COLUMNS = ("yahoo_symbol", "ticker_yahoo", "ticker", "symbol", "simbolo")
TYPE_COLUMNS = ("tipo_valor", "tipo de valor", "tipo_instrumento", "instrument_type", "tipo")
MARKET_COLUMNS = ("mercado", "tipo_mercado", "tipo de mercado", "market")


def _column(row, names):
    normalized = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        if name in normalized and pd.notna(normalized[name]):
            return str(normalized[name]).strip()
    return ""


def import_official_export(path: Path):
    """Only accept explicit Yahoo symbols, not BMV issuer keys without a series mapping."""
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str)
    elif path.suffix.lower() == ".csv":
        try:
            df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(path, dtype=str, encoding="latin-1")
    else:
        raise ValueError("Expected .csv, .xlsx or .xls")
    symbols, rejected = [], []
    for i, row in enumerate(df.to_dict("records"), 2):
        symbol = _column(row, SYMBOL_COLUMNS).upper()
        typ = _column(row, TYPE_COLUMNS).upper()
        market = _column(row, MARKET_COLUMNS).upper()
        if market and any(s in market for s in ("GLOBAL", "SIC", "DEUDA")):
            rejected.append({"row": i, "symbol": symbol, "reason": "NON_LOCAL_MARKET"})
        elif typ and any(s in typ for s in ("ETF", "FIBRA", "FONDO", "CKD", "CERPI", "DEUDA")):
            rejected.append({"row": i, "symbol": symbol, "reason": "NON_COMMON_EQUITY_TYPE"})
        elif not TICKER.fullmatch(symbol):
            rejected.append({"row": i, "symbol": symbol, "reason": "EXPLICIT_YAHOO_SYMBOL_REQUIRED"})
        else:
            symbols.append(symbol)
    return list(dict.fromkeys(symbols)), rejected


def build_catalogue(*, official_path=None, yahoo_target=1000):
    sources = {}
    for symbol in MEXICO_TICKERS + BREAKOUT_TEST_SYMBOLS:
        if symbol.upper().endswith(".MX"):
            sources.setdefault(symbol.upper(), set()).add("CONFIG")
    yahoo_symbols = _discover_region("mx", yahoo_target)
    for symbol in yahoo_symbols:
        if TICKER.fullmatch(symbol.upper()):
            sources.setdefault(symbol.upper(), set()).add("YAHOO_DISCOVERY")
    rejected = []
    if official_path:
        official_symbols, rejected = import_official_export(Path(official_path))
        for symbol in official_symbols:
            sources.setdefault(symbol, set()).add("OFFICIAL_EXPORT_EXPLICIT_MAPPING")
    rows = []
    for symbol, origin in sorted(sources.items()):
        # Conservative review gate: a Yahoo quoteType of EQUITY alone does not
        # establish whether an instrument is an ordinary share.
        suspect = any(marker in symbol for marker in EXCLUDE_MARKERS)
        rows.append({"symbol": symbol, "sources": "|".join(sorted(origin)),
                     "classification": "REVIEW_NON_COMMON_INSTRUMENT" if suspect else "UNVERIFIED_EQUITY",
                     "eligible_for_automatic_radar": False})
    return {"generated_utc": datetime.now(timezone.utc).isoformat(),
            "requested_yahoo_mx": yahoo_target, "yahoo_discovered": len(yahoo_symbols),
            "catalogue_size": len(rows), "rows": rows,
            "official_rejected_count": len(rejected), "official_rejected": rejected,
            "limitations": ["SYMBOL_MAPPING_REQUIRES_EXPLICIT_YAHOO_TICKER",
                            "CLASSIFICATION_NOT_VERIFIED",
                            "CATALOGUE_IS_NOT_AN_AUTOMATIC_TRADING_UNIVERSE"]}


def main(argv=None):
    p = argparse.ArgumentParser(description="Reviewable Mexican equity catalogue (research only)")
    p.add_argument("--official-file", type=Path, default=None,
                   help="Optional BMV CSV/XLSX enriched with explicit yahoo_symbol column")
    p.add_argument("--yahoo-target", type=int, default=1000)
    p.add_argument("--output", type=Path, default=Path(".cache/mx_catalogue.csv"))
    args = p.parse_args(argv)
    if not 1 <= args.yahoo_target <= 3000:
        p.error("--yahoo-target must be 1..3000")
    result = build_catalogue(official_path=args.official_file, yahoo_target=args.yahoo_target)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=("symbol", "sources", "classification", "eligible_for_automatic_radar"))
        writer.writeheader()
        writer.writerows(result["rows"])
    diagnostic = args.output.with_suffix(".diagnostics.json")
    diagnostic.write_text(json.dumps({k: v for k, v in result.items() if k != "rows"},
                                     ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"MX catalogue={result['catalogue_size']} | Yahoo={result['yahoo_discovered']} | "
          f"Official rejected={result['official_rejected_count']}")
    print(f"Saved {args.output} and {diagnostic}")
    print("All entries require instrument classification review before automatic radar inclusion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
