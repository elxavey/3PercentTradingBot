"""Refresh only scanner-selected cached histories; never accept invalid replacement bars."""
import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf
from data_fetcher import _history_cache_path
from tradepilot.v6_actual_scanner_report_cli import report
from tradepilot.v6_cached_history_bridge import load_cached_history


def refresh(db, as_of, top=20, period="6mo"):
    ranked, scanner = report(db, as_of, limit=top)
    rows = []
    for candidate in ranked:
        symbol = candidate["symbol"]
        path = _history_cache_path(symbol)
        try:
            data = yf.Ticker(symbol).history(period=period)
            if data is None or data.empty:
                raise ValueError("NO_PROVIDER_HISTORY")
            # Validate candidate in a temporary file before replacing cache.
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", dir=path.parent, delete=False,
                encoding="utf-8") as temp:
                temporary = Path(temp.name)
                data.to_csv(temp)
            try:
                # The cache reader is deliberately strict; keep old cache on failure.
                import pandas as pd
                from data_fetcher import _normalize_cached_history_index
                checked = pd.read_csv(temporary, index_col=0)
                checked = _normalize_cached_history_index(checked, symbol)
                required = ["Open", "High", "Low", "Close", "Volume"]
                if checked.empty or any(x not in checked for x in required):
                    raise ValueError("INVALID_COLUMNS")
                n = checked[required].apply(pd.to_numeric, errors="coerce")
                if n.isna().any().any() or (n[["Open","High","Low","Close"]] <= 0).any().any() or (n["Volume"] < 0).any():
                    raise ValueError("INVALID_VALUES")
                if ((n["High"] < n[["Open","Low","Close"]].max(axis=1)) |
                        (n["Low"] > n[["Open","Close"]].min(axis=1))).any():
                    raise ValueError("INVALID_OHLC")
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            rows.append({"symbol": symbol, "status": "UPDATED", "bars": len(data),
                         "last_bar": str(data.index[-1])})
        except Exception as exc:
            rows.append({"symbol": symbol, "status": "SKIPPED",
                         "reason": type(exc).__name__ + ": " + str(exc)[:120]})
    return {"as_of": as_of, "scanner_status": scanner["status"],
            "refreshed": sum(x["status"] == "UPDATED" for x in rows),
            "results": rows, "orders_sent": 0}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="data/tradepilot.db")
    p.add_argument("--as-of", required=True)
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--period", default="6mo")
    a = p.parse_args(argv)
    print(json.dumps(refresh(a.db, a.as_of, a.top, a.period), indent=2))


if __name__ == "__main__":
    main()
