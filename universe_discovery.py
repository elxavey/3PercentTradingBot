from time import perf_counter

import yfinance as yf
from yfinance import EquityQuery


def is_common_equity_quote(quote: dict) -> bool:
    """Conservative instrument screen: reject known ETFs/funds/FIBRAs, do not infer missing type."""
    symbol = str(quote.get("symbol") or "").upper()
    kind = str(quote.get("quoteType") or "").upper()
    name = str(quote.get("longName") or quote.get("shortName") or "").upper()
    if not symbol or kind != "EQUITY":
        return False
    if any(token in name for token in ("ETF", "EXCHANGE TRADED FUND", "FIBRA", "FIDEICOMISO DE INVERSION EN BIENES RAICES")):
        return False
    if symbol.endswith(".MX") and (symbol.startswith(("NAFTRAC", "IVVPESO", "VMEX", "MEXTRAC", "FIBRA")) or symbol.startswith(("FUNO", "FMTY", "FIBRAMQ", "DANHOS", "TERRA13", "FPLUS", "FSHOP", "FIBRAPL", "FIBRAUP", "FIBRATC", "FIBRAHD", "FIBRAST", "FIBRANQ"))):
        return False
    return True


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
            if is_common_equity_quote(quote) and symbol not in symbols:
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
