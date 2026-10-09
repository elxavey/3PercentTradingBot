"""Optional, review-only BMV research universe overlay; no automatic approval."""
import csv
from pathlib import Path

DEFAULT_FILE = Path(".cache/mx_bmv_candidate_validation.csv")

def load_bmv_research_symbols(path=DEFAULT_FILE, min_median_volume=10000, min_bars=350):
    """Read validated-history candidates, NOT verified issuer mappings."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"BMV validation CSV missing: {path}. Run mx_bmv_validate_cli first.")
    symbols, seen = [], set()
    counts = {"rows": 0, "wrong_instrument": 0, "manual_issuer_review": 0,
              "short_history": 0, "low_volume": 0, "selected": 0}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            counts["rows"] += 1
            symbol = row.get("symbol", "").strip().upper()
            if row.get("quote_type", "").strip().upper() != "EQUITY" or not symbol.endswith(".MX"):
                counts["wrong_instrument"] += 1
                continue
            if row.get("mapping_status") != "SERIES_AND_ISSUER_REVIEW":
                counts["manual_issuer_review"] += 1
                continue
            try:
                bars = int(float(row.get("daily_bars") or 0))
                volume = float(row.get("median_volume_last_60") or 0)
            except ValueError:
                counts["short_history"] += 1
                continue
            if row.get("history_status") != "ENOUGH_BARS" or bars < min_bars:
                counts["short_history"] += 1
                continue
            if volume < min_median_volume:
                counts["low_volume"] += 1
                continue
            if symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)
    counts["selected"] = len(symbols)
    return symbols, counts
