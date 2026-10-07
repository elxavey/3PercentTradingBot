# Initial universe for the 3% Trading Bot scanner.
# Yahoo Finance uses the .MX suffix for Bolsa Mexicana de Valores symbols.
MEXICO_TICKERS = [
    "ALSEA.MX",
    "WALMEX.MX",
    "TLEVISA-CPO.MX",
    "GMEXICOB.MX",
]

USA_TICKERS = [
    "AAPL",
    "AMZN",
]

TICKERS = MEXICO_TICKERS + USA_TICKERS

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
