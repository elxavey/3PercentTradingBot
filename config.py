APP_VERSION = "0.3.0"
APP_BUILD = "Universe Manager v0.1"

# Initial universe for the 3% Trading Bot scanner.
# Yahoo Finance uses the .MX suffix for Bolsa Mexicana de Valores symbols.
MEXICO_TICKERS = [
    "ALSEA.MX",
    "WALMEX.MX",
    "TLEVISACPO.MX",
    "GMEXICOB.MX",
    "FEMSAUBD.MX",
    "CEMEXCPO.MX",
    "GFNORTEO.MX",
    "BIMBOA.MX",
    "GAPB.MX",
    "ASURB.MX",
]

USA_TICKERS = [
    "AAPL",
    "AMZN",
]

TICKERS = MEXICO_TICKERS + USA_TICKERS

BROAD_US_TICKERS = [
    "MSFT", "GOOGL", "META", "NVDA", "TSLA", "JPM", "V", "MA", "HD", "COST",
    "NFLX", "AMD", "AVGO", "ORCL", "CRM", "ADBE", "QCOM", "TXN", "INTC", "IBM",
    "KO", "PEP", "MCD", "SBUX", "NKE", "DIS", "WMT", "TGT", "LOW", "CAT",
    "BA", "GE", "HON", "UPS", "FDX", "XOM", "CVX", "COP", "SLB", "JNJ",
    "PFE", "MRK", "ABBV", "LLY", "UNH", "BAC", "GS", "MS", "AXP", "PYPL",
]

UNIVERSES = {
    "Test - 12 symbols": TICKERS,
    "Broad MX + USA - 62 symbols": TICKERS + BROAD_US_TICKERS,
}

UNIVERSE_PRE_SCREEN = {
    "min_price": 5.0,
    "min_history_days": 252,
    "min_avg_traded_value": 5_000_000,
}

# ETFs are not part of the first 3% strategy universe.
# The original ETF engine is preserved and can be enabled later.
ETF_TICKERS = []

PASS_THRESHOLD = 0.80
ETF_PASS_THRESHOLD = 0.80

RULES_FUNDAMENTAL = {
    "pe_ratio":  {"max": 25,   "enabled": True},
    "pb_ratio":  {"max": 2,    "enabled": True},
    "peg_ratio": {"max": 1.0,  "enabled": True},
    "fcf_yield": {"min": 0.03, "enabled": True},
    "de_ratio":  {"max": 1,    "enabled": True},
}

RULES_TECHNICAL = {
    "rsi_breakout":     {"min": 0, "max": 50, "enabled": True},
    "macd_crossover":   {"enabled": True},
    "bb_squeeze":       {
        "enabled":              True,
        "window":               60,
        "percentile_threshold": 0.20,
        "lookback_periods":     3,
    },
    "ma_confluence":    {"enabled": True},
    "rel_volume_surge": {"min_multiplier": 1.5, "enabled": True},
    "golden_cross":     {"lookback_days": 90, "enabled": True},
    "death_cross":      {"lookback_days": 90, "enabled": False},
}

# Quality Gate v0.1 — eligibility only, not an entry signal.
# Initial research thresholds; these will be validated and tuned with backtests.
QUALITY_GATE = {
    "MX": {
        "min_price": 5.0,
        "min_market_cap": 10_000_000_000,       # MXN
        "min_avg_traded_value": 5_000_000,      # MXN/day, 20-session average
        "min_history_days": 252,
    },
    "US": {
        "min_price": 5.0,
        "min_market_cap": 2_000_000_000,        # USD
        "min_avg_traded_value": 10_000_000,     # USD/day, 20-session average
        "min_history_days": 252,
    },
}

# Opportunity Score v0.1 — ranking only. Weights are explicit so they can
# later be validated/optimized with backtesting rather than guessed silently.
OPPORTUNITY_SCORE = {
    "weights": {
        "trend": 30,
        "rsi": 25,
        "rvol": 20,
        "atr": 25,
    },
    "rsi": {
        "ideal_min": 50,
        "ideal_max": 65,
        "extended_max": 75,
    },
    "rvol": {
        "strong": 1.5,
        "normal": 1.0,
    },
    "atr_pct": {
        "ideal_min": 2.0,
        "ideal_max": 4.5,
        "minimum": 1.0,
    },
}
