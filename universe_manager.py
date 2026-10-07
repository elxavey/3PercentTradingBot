from time import perf_counter

from config import UNIVERSE_PRE_SCREEN
from data_fetcher import get_price_history


def pre_screen_symbol(ticker: str) -> dict:
    started = perf_counter()
    history = get_price_history(ticker)

    if history is None or history.empty:
        return {
            "ticker": ticker,
            "passed": False,
            "reason": "NO_HISTORY",
            "history": None,
            "seconds": round(perf_counter() - started, 3),
        }

    price = float(history["Close"].iloc[-1])
    history_days = len(history)
    recent = history.tail(20)
    avg_traded_value = float((recent["Close"] * recent["Volume"]).mean())

    checks = {
        "price": price >= UNIVERSE_PRE_SCREEN["min_price"],
        "history": history_days >= UNIVERSE_PRE_SCREEN["min_history_days"],
        "liquidity": avg_traded_value >= UNIVERSE_PRE_SCREEN["min_avg_traded_value"],
    }

    return {
        "ticker": ticker,
        "passed": all(checks.values()),
        "reason": "PASS" if all(checks.values()) else ", ".join(k for k, ok in checks.items() if not ok),
        "history": history,
        "price": price,
        "history_days": history_days,
        "avg_traded_value": avg_traded_value,
        "seconds": round(perf_counter() - started, 3),
    }


def run_universe_pre_screen(tickers: list[str], progress_callback=None) -> dict:
    started = perf_counter()
    passed = []
    excluded = []

    for index, ticker in enumerate(tickers):
        result = pre_screen_symbol(ticker)
        if result["passed"]:
            passed.append(result)
        else:
            excluded.append(result)
        if progress_callback:
            progress_callback(index + 1, len(tickers), ticker)

    return {
        "total": len(tickers),
        "passed": passed,
        "excluded": excluded,
        "seconds": round(perf_counter() - started, 3),
    }
