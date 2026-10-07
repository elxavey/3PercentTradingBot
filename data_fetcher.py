import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

import pandas as pd
import yfinance as yf

CACHE_DIR = Path(".cache")
FUNDAMENTALS_CACHE_FILE = CACHE_DIR / "fundamentals.json"
FUNDAMENTALS_TTL_HOURS = 24
HISTORY_CACHE_DIR = CACHE_DIR / "history"
HISTORY_TTL_HOURS = 6


def _load_fundamentals_cache() -> dict:
    if not FUNDAMENTALS_CACHE_FILE.exists():
        return {}
    try:
        return json.loads(FUNDAMENTALS_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_fundamentals_cache(cache: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    FUNDAMENTALS_CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _cache_is_fresh(entry: dict) -> bool:
    try:
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
        return datetime.now(timezone.utc) - fetched_at < timedelta(hours=FUNDAMENTALS_TTL_HOURS)
    except (KeyError, TypeError, ValueError):
        return False


def get_fundamentals(ticker: str, force_refresh: bool = False) -> tuple[dict | None, dict]:
    started = perf_counter()
    cache = _load_fundamentals_cache()
    cached = cache.get(ticker)

    if not force_refresh and cached and _cache_is_fresh(cached):
        return cached["data"], {
            "cache_hit": True,
            "seconds": round(perf_counter() - started, 3),
        }

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        market_cap = info.get("marketCap")
        free_cashflow = info.get("freeCashflow")
        fcf_yield = None
        if free_cashflow and market_cap and market_cap > 0:
            fcf_yield = free_cashflow / market_cap

        data = {
            "ticker": ticker,
            "market_cap": market_cap,
            "pe_ratio": info.get("trailingPE"),
            "pb_ratio": info.get("priceToBook"),
            "peg_ratio": info.get("pegRatio"),
            "fcf_yield": fcf_yield,
            "de_ratio": info.get("debtToEquity"),
            "name": info.get("shortName", ticker),
            "sector": info.get("sector", "N/A"),
            "price": info.get("currentPrice"),
            "currency": info.get("currency"),
            "revenue": info.get("totalRevenue"),
            "net_income": info.get("netIncomeToCommon"),
            "free_cashflow": free_cashflow,
            "total_cash": info.get("totalCash"),
            "total_debt": info.get("totalDebt"),
        }
        cache[ticker] = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        _save_fundamentals_cache(cache)
        return data, {
            "cache_hit": False,
            "seconds": round(perf_counter() - started, 3),
        }
    except Exception as e:
        print(f"  [!] Could not fetch fundamentals for {ticker}: {e}")
        return None, {
            "cache_hit": False,
            "seconds": round(perf_counter() - started, 3),
        }


def _history_cache_path(ticker: str) -> Path:
    safe_ticker = ticker.replace("/", "_").replace("\\", "_")
    return HISTORY_CACHE_DIR / f"{safe_ticker}.csv"


def _history_cache_is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - modified < timedelta(hours=HISTORY_TTL_HOURS)


def get_price_history(
    ticker: str,
    period: str = "2y",
    force_refresh: bool = False,
    return_timing: bool = False,
):
    started = perf_counter()
    cache_path = _history_cache_path(ticker)

    if not force_refresh and _history_cache_is_fresh(cache_path):
        try:
            df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            if not df.empty:
                timing = {"cache_hit": True, "seconds": round(perf_counter() - started, 3)}
                return (df, timing) if return_timing else df
        except (OSError, ValueError, pd.errors.ParserError):
            pass

    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period)
        if df.empty:
            print(f"  [!] No price history for {ticker}")
            timing = {"cache_hit": False, "seconds": round(perf_counter() - started, 3)}
            return (None, timing) if return_timing else None

        HISTORY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache_path)
        timing = {"cache_hit": False, "seconds": round(perf_counter() - started, 3)}
        return (df, timing) if return_timing else df
    except Exception as e:
        print(f"  [!] Could not fetch price history for {ticker}: {e}")
        timing = {"cache_hit": False, "seconds": round(perf_counter() - started, 3)}
        return (None, timing) if return_timing else None
