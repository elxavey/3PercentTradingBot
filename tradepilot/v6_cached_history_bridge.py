"""Read-only bridge for scanner-selected symbols to existing cached histories."""
from pathlib import Path
import pandas as pd
from data_fetcher import _history_cache_path, _normalize_cached_history_index


def load_cached_history(symbol):
    path = _history_cache_path(symbol)
    if not path.is_file():
        return None, "CACHE_MISSING"
    try:
        data = pd.read_csv(path, index_col=0)
        data = _normalize_cached_history_index(data, symbol)
        required = ("Open", "High", "Low", "Close", "Volume")
        if data.empty or any(column not in data.columns for column in required):
            return None, "INVALID_CACHE_COLUMNS"
        values = data.loc[:, required].apply(pd.to_numeric, errors="coerce")
        if values.isna().any().any() or (values.loc[:, ("Open", "High", "Low", "Close")] <= 0).any().any():
            return None, "INVALID_CACHE_VALUES"
        if (values["Volume"] < 0).any():
            return None, "INVALID_VOLUME"
        if ((values["High"] < values[["Open", "Close", "Low"]].max(axis=1)) | (values["Low"] > values[["Open", "Close"]].min(axis=1))).any():
            return None, "INVALID_OHLC"
        data.loc[:, required] = values
        return data, ""
    except (OSError, ValueError, TypeError, pd.errors.ParserError):
        return None, "CACHE_READ_ERROR"
