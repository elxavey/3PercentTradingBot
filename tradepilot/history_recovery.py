"""Conservative, bounded repair of missing daily provider candles.

Only real provider-returned OHLCV bars are accepted. No forward fill or synthesis.
"""
from __future__ import annotations

from datetime import timedelta
import pandas as pd


def recover_missing_sessions(history: pd.DataFrame, missing_dates: list[str], *,
                             symbol: str, fetcher=None, max_missing: int = 5) -> tuple[pd.DataFrame, dict]:
    """Fetch each absent date independently and merge only validated daily bars."""
    if not isinstance(history, pd.DataFrame) or history.empty:
        raise ValueError("nonempty history required")
    if not isinstance(history.index, pd.DatetimeIndex) or not history.index.is_unique:
        raise ValueError("unique DatetimeIndex required")
    if not isinstance(missing_dates, list) or not 0 < len(missing_dates) <= max_missing:
        return history.copy(), {"state": "NOT_ATTEMPTED", "recovered": [], "unresolved": missing_dates,
                                "reason": "MISSING_COUNT_OUTSIDE_SAFE_LIMIT"}
    if fetcher is None:
        import yfinance as yf
        fetcher = lambda ticker, start, end: yf.Ticker(ticker).history(
            start=start, end=end, interval="1d", auto_adjust=False)
    repaired = history.copy()
    recovered, unresolved = [], []
    required = ["Open", "High", "Low", "Close", "Volume"]
    existing_dates = {x.date() for x in repaired.index}
    for date_text in missing_dates:
        try:
            day = pd.Timestamp(date_text).date()
            if day in existing_dates:
                unresolved.append(date_text)
                continue
            # Explicit [start, end) range; never take an adjacent day's bar.
            fragment = fetcher(symbol, day.isoformat(),
                               (day + timedelta(days=1)).isoformat())
            if not isinstance(fragment, pd.DataFrame) or fragment.empty:
                unresolved.append(date_text)
                continue
            if any(k not in fragment.columns for k in required):
                unresolved.append(date_text)
                continue
            matches = fragment.loc[[stamp.date() == day for stamp in fragment.index]]
            if len(matches) != 1:
                unresolved.append(date_text)
                continue
            bar = matches.iloc[0]
            op, hi, lo, cl, vol = [float(bar[k]) for k in required]
            from math import isfinite
            if (not all(isfinite(x) for x in (op,hi,lo,cl,vol))
                    or min(op,hi,lo,cl) <= 0 or vol < 0
                    or hi < max(op,cl,lo) or lo > min(op,cl,hi)):
                unresolved.append(date_text)
                continue
            # Normalize recovered timestamp to the index's own daily convention.
            stamp = repaired.index[0].replace(year=day.year, month=day.month, day=day.day)
            if stamp.date() != day or stamp in repaired.index:
                unresolved.append(date_text)
                continue
            new_row = pd.DataFrame([{col: bar[col] if col in fragment else float("nan")
                                     for col in repaired.columns}], index=pd.DatetimeIndex([stamp]))
            repaired = pd.concat([repaired, new_row]).sort_index()
            existing_dates.add(day)
            recovered.append(date_text)
        except (ValueError, TypeError, KeyError, OverflowError, AttributeError, IndexError):
            unresolved.append(date_text)
        except Exception:
            # Provider outages and rate limits must not bypass validation.
            unresolved.append(date_text)
    return repaired, {"state": "RECOVERED" if not unresolved else "PARTIAL_OR_FAILED",
                      "recovered": recovered, "unresolved": unresolved,
                      "source": "PROVIDER_DAILY_HISTORY", "synthetic_bars": 0}
