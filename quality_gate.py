import pandas as pd

from config import QUALITY_GATE


def evaluate_quality_gate(ticker: str, fundamentals: dict, price_history: pd.DataFrame) -> dict:
    """Determine whether a stock is eligible for strategy research.

    A Quality Gate pass is not a buy signal. It only means the security meets
    basic size, liquidity, price, and history requirements.
    """
    market = "MX" if ticker.upper().endswith(".MX") else "US"
    rules = QUALITY_GATE[market]

    close = price_history["Close"]
    volume = price_history["Volume"]
    price = float(close.iloc[-1])
    history_days = int(len(price_history))

    recent = pd.DataFrame({"Close": close, "Volume": volume}).tail(20)
    avg_traded_value = float((recent["Close"] * recent["Volume"]).mean())

    market_cap = fundamentals.get("market_cap")
    checks = {
        "price": price >= rules["min_price"],
        "market_cap": market_cap is not None and market_cap >= rules["min_market_cap"],
        "liquidity": avg_traded_value >= rules["min_avg_traded_value"],
        "history": history_days >= rules["min_history_days"],
    }

    return {
        "passed": all(checks.values()),
        "market": market,
        "checks": checks,
        "market_cap": market_cap,
        "avg_traded_value": avg_traded_value,
        "history_days": history_days,
        "currency": fundamentals.get("currency") or ("MXN" if market == "MX" else "USD"),
    }
