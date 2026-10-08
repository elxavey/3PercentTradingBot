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


def verified_eodhd_daily(symbol: str, start: str, end: str, *,
                         reference: pd.DataFrame, fetcher=eodhd_daily,
                         max_relative_difference: float = 0.015):
    """Require adjacent provider closing prices to agree with Yahoo basis.

    No cross-provider stitching when split/dividend adjustments differ.
    """
    from datetime import timedelta
    if not isinstance(reference, pd.DataFrame) or reference.empty:
        return pd.DataFrame()
    target = date.fromisoformat(start)
    dates = sorted({stamp.date() for stamp in reference.index})
    before = [d for d in dates if d < target]
    after = [d for d in dates if d > target]
    if not before or not after:
        return pd.DataFrame()
    neighbors = [before[-1], after[0]]
    for day in neighbors:
        try:
            remote = fetcher(symbol, day.isoformat(),
                             (day + timedelta(days=1)).isoformat())
            if not isinstance(remote, pd.DataFrame) or len(remote) != 1:
                return pd.DataFrame()
            if remote.index[0].date() != day:
                return pd.DataFrame()
            remote_close = float(remote.iloc[0]["Close"])
            local_close = float(reference.loc[[x.date() == day for x in reference.index]].iloc[0]["Close"])
            from math import isfinite
            if not all(isfinite(x) and x > 0 for x in (remote_close,local_close)):
                return pd.DataFrame()
            if abs(remote_close / local_close - 1) > max_relative_difference:
                return pd.DataFrame()
        except Exception:
            return pd.DataFrame()
    return fetcher(symbol, start, end)
