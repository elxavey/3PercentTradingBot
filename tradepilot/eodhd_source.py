"""Optional EODHD secondary daily-bar source. No credentials in source/logs."""
from __future__ import annotations
from datetime import date
import os
import re
import pandas as pd


def eodhd_daily(symbol: str, start: str, end: str, *, token=None, requester=None):
    """Return provider raw OHLCV; caller must validate and compare adjustment basis.

    end is exclusive (Yahoo convention), EODHD 'to' is inclusive.
    """
    key = token if token is not None else os.environ.get("EODHD_API_TOKEN", "")
    if not key or not isinstance(key, str):
        return pd.DataFrame()
    if not re.fullmatch(r"[A-Za-z0-9^_-]+\.(?:MX|US)", symbol.upper()):
        raise ValueError("unsupported EODHD ticker")
    first, last_exclusive = date.fromisoformat(start), date.fromisoformat(end)
    if (last_exclusive - first).days != 1:
        raise ValueError("one day request required")
    if requester is None:
        import requests
        requester = requests.get
    response = requester(
        f"https://eodhd.com/api/eod/{symbol.upper()}",
        params={"api_token": key, "from": start, "to": start,
                "period": "d", "fmt": "json"}, timeout=12)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return pd.DataFrame()
    rows = []
    for bar in payload:
        if not isinstance(bar, dict) or bar.get("date") != start:
            continue
        rows.append({"Date": bar["date"], "Open": bar.get("open"),
                     "High": bar.get("high"), "Low": bar.get("low"),
                     "Close": bar.get("close"), "Volume": bar.get("volume")})
    if len(rows) != 1:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index(pd.to_datetime([rows[0]["Date"]])).drop(columns=["Date"])
