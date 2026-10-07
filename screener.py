from time import perf_counter
from config import (
    TICKERS, ETF_TICKERS,
    RULES_FUNDAMENTAL, RULES_TECHNICAL,
    PASS_THRESHOLD, ETF_PASS_THRESHOLD
)
from data_fetcher import get_fundamentals, get_price_history
from fundamental_rules import run_fundamental_checks, get_fundamental_values
from technical_rules import run_technical_checks, get_technical_values, get_scanner_metrics
from quality_gate import evaluate_quality_gate
from opportunity_score import calculate_opportunity_score


def score_stock(
    ticker: str,
    etf_mode: bool = False,
    fund_rules: dict = None,
    tech_rules: dict = None,
    threshold: float = None,
    price_history=None,
) -> dict | None:
    if fund_rules is None:
        fund_rules = RULES_FUNDAMENTAL
    if tech_rules is None:
        tech_rules = RULES_TECHNICAL
    if threshold is None:
        threshold = ETF_PASS_THRESHOLD if etf_mode else PASS_THRESHOLD

    print(f"  Analyzing {ticker}...")
    ticker_started = perf_counter()

    history_started = perf_counter()
    reused_history = price_history is not None
    if price_history is None:
        price_history = get_price_history(ticker)
    history_seconds = perf_counter() - history_started
    if price_history is None:
        return None

    technical_results = run_technical_checks(price_history, tech_rules)
    technical_values  = get_technical_values(price_history, tech_rules)
    scanner_metrics   = get_scanner_metrics(price_history)

    if etf_mode:
        all_results       = technical_results
        raw_values        = {"technical": technical_values, "fundamental": {}}
        name              = ticker
        sector            = "ETF"
        price             = float(price_history["Close"].iloc[-1])
    else:
        fundamentals, metadata_timing = get_fundamentals(ticker)
        metadata_seconds = metadata_timing["seconds"]
        metadata_cache_hit = metadata_timing["cache_hit"]
        if fundamentals is None:
            return None
        quality_gate = evaluate_quality_gate(ticker, fundamentals, price_history)
        opportunity = calculate_opportunity_score(scanner_metrics, quality_gate["passed"])
        fundamental_results = run_fundamental_checks(fundamentals, fund_rules)
        fundamental_values  = get_fundamental_values(fundamentals, fund_rules)
        all_results         = {**fundamental_results, **technical_results}
        raw_values          = {"fundamental": fundamental_values, "technical": technical_values}
        name                = fundamentals.get("name", ticker)
        sector              = fundamentals.get("sector", "N/A")
        price               = fundamentals.get("price") or float(price_history["Close"].iloc[-1])

    total_rules  = len(all_results)
    rules_passed = sum(1 for v in all_results.values() if v)
    score        = rules_passed / total_rules if total_rules > 0 else 0

    return {
        "ticker":       ticker,
        "name":         name,
        "sector":       sector,
        "price":        price,
        "score":        score,
        "rules_passed": rules_passed,
        "total_rules":  total_rules,
        "passed":       score >= threshold,
        "rule_details": all_results,
        "raw_values":   raw_values,
        "rsi":          scanner_metrics["rsi"],
        "rvol":         scanner_metrics["rvol"],
        "atr_pct":      scanner_metrics["atr_pct"],
        "trend":        scanner_metrics["trend"],
        "quality_gate": quality_gate if not etf_mode else None,
        "opportunity": opportunity if not etf_mode else None,
        "timing": {
            "history_seconds": round(history_seconds, 3),
            "history_reused": reused_history,
            "metadata_seconds": round(metadata_seconds, 3) if not etf_mode else 0.0,
            "metadata_cache_hit": metadata_cache_hit if not etf_mode else False,
            "total_seconds": round(perf_counter() - ticker_started, 3),
        },
    }


def run_screener(
    tickers: list = None,
    etf_tickers: list = None,
    fund_rules: dict = None,
    tech_rules: dict = None,
    stock_threshold: float = None,
    etf_threshold: float = None,
) -> list:
    if tickers is None:
        tickers = TICKERS
    if etf_tickers is None:
        etf_tickers = ETF_TICKERS

    results = []

    for ticker in tickers:
        result = score_stock(ticker, etf_mode=False,
                             fund_rules=fund_rules, tech_rules=tech_rules,
                             threshold=stock_threshold)
        if result:
            results.append(result)

    for ticker in etf_tickers:
        result = score_stock(ticker, etf_mode=True,
                             fund_rules=fund_rules, tech_rules=tech_rules,
                             threshold=etf_threshold)
        if result:
            results.append(result)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results