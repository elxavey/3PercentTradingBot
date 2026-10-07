from time import perf_counter

import yfinance as yf
from yfinance import EquityQuery


def _discover_region(region: str, target: int) -> list[str]:
    """Discover liquid equities from Yahoo Finance with pagination."""
    symbols = []
    offset = 0

    query = EquityQuery("and", [
        EquityQuery("eq", ["region", region]),
        EquityQuery("gte", ["intradayprice", 5]),
        EquityQuery("gt", ["avgdailyvol3m", 100_000]),
    ])

    while len(symbols) < target:
        page_size = min(250, target - len(symbols))
        response = yf.screen(
            query,
            offset=offset,
            size=page_size,
            sortField="avgdailyvol3m",
            sortAsc=False,
        )
        quotes = response.get("quotes", [])
        if not quotes:
            break

        for quote in quotes:
            symbol = quote.get("symbol")
            quote_type = quote.get("quoteType")
            if symbol and (not quote_type or quote_type == "EQUITY") and symbol not in symbols:
                symbols.append(symbol)

        if len(quotes) < page_size:
            break
        offset += page_size

    return symbols[:target]


def discover_dynamic_universe(target_size: int) -> dict:
    """Build a fresh MX + USA universe. Prefer MX names, then fill with US."""
    started = perf_counter()

    # Reserve up to 20% for Mexico; any unused capacity is filled from the US.
    mx_target = max(10, int(target_size * 0.20))
    mx_symbols = _discover_region("mx", mx_target)

    us_target = target_size - len(mx_symbols)
    us_symbols = _discover_region("us", us_target)

    symbols = []
    for symbol in mx_symbols + us_symbols:
        if symbol not in symbols:
            symbols.append(symbol)

    # If Yahoo returned fewer names than requested for either region, top up US.
    if len(symbols) < target_size:
        extra_us = _discover_region("us", target_size)
        for symbol in extra_us:
            if symbol not in symbols:
                symbols.append(symbol)
            if len(symbols) >= target_size:
                break

    return {
        "symbols": symbols[:target_size],
        "requested": target_size,
        "discovered": min(len(symbols), target_size),
        "mx": sum(1 for s in symbols[:target_size] if s.endswith(".MX")),
        "us": sum(1 for s in symbols[:target_size] if not s.endswith(".MX")),
        "seconds": round(perf_counter() - started, 3),
        "source": "Yahoo Finance EquityQuery",
    }
