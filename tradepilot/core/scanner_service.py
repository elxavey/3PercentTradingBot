"""UI-independent orchestration of the legacy v0.4.0 scanner.

Preserves discovery, pre-screen, scoring, history reuse and opportunity ordering.
No Streamlit, scheduler, persistence or order execution is imported here.
"""
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from config import (
    ETF_PASS_THRESHOLD, PASS_THRESHOLD,
    RULES_FUNDAMENTAL, RULES_TECHNICAL,
)
from screener import score_stock
from universe_discovery import discover_dynamic_universe
from universe_manager import run_universe_pre_screen

ProgressCallback = Callable[[int, int, str], None]


@dataclass
class ScanOutcome:
    results: list[dict]
    universe_result: dict
    discovery_result: dict | None
    scan_seconds: float

    @property
    def quality_passed(self) -> list[dict]:
        return [
            result for result in self.results
            if result.get("quality_gate") and result["quality_gate"]["passed"]
        ]


def run_scan(
    *,
    tickers: list[str] | None = None,
    etf_tickers: list[str] | None = None,
    dynamic_target: int | None = None,
    fund_rules: dict | None = None,
    tech_rules: dict | None = None,
    stock_threshold: float | None = None,
    etf_threshold: float | None = None,
    pre_screen_progress: ProgressCallback | None = None,
    analysis_progress: ProgressCallback | None = None,
) -> ScanOutcome:
    """Run the same pipeline previously embedded in app.py.

    A dynamic_target selects Yahoo discovery; otherwise tickers are used as-is.
    Empty discovery returns an empty outcome rather than silently using defaults.
    Dependencies are deliberately patchable for deterministic tests.
    """
    if dynamic_target is not None and dynamic_target <= 0:
        raise ValueError("dynamic_target must be positive")
    if dynamic_target is not None and tickers:
        raise ValueError("Provide either tickers or dynamic_target")
    started = perf_counter()
    discovery_result = None
    symbols = list(tickers or [])
    etfs = list(etf_tickers or [])
    if dynamic_target is not None:
        discovery_result = discover_dynamic_universe(dynamic_target)
        symbols = discovery_result["symbols"]
        if not symbols:
            return ScanOutcome(
                results=[],
                universe_result={
                    "total": 0, "passed": [], "excluded": [],
                    "history_cache_hits": 0, "seconds": 0.0,
                },
                discovery_result=discovery_result,
                scan_seconds=perf_counter() - started,
            )

    universe_result = run_universe_pre_screen(symbols, pre_screen_progress)
    passed = universe_result["passed"]
    history_by_symbol = {row["ticker"]: row["history"] for row in passed}
    all_symbols = [(row["ticker"], False) for row in passed]
    all_symbols.extend((symbol, True) for symbol in etfs)
    results = []
    for index, (symbol, is_etf) in enumerate(all_symbols):
        if analysis_progress:
            analysis_progress(index + 1, len(all_symbols), symbol)
        result = score_stock(
            symbol,
            etf_mode=is_etf,
            fund_rules=fund_rules if fund_rules is not None else RULES_FUNDAMENTAL,
            tech_rules=tech_rules if tech_rules is not None else RULES_TECHNICAL,
            threshold=(
                (etf_threshold if etf_threshold is not None else ETF_PASS_THRESHOLD)
                if is_etf else
                (stock_threshold if stock_threshold is not None else PASS_THRESHOLD)
            ),
            price_history=None if is_etf else history_by_symbol.get(symbol),
        )
        if result:
            results.append(result)
    results.sort(
        key=lambda item: (item.get("opportunity") or {}).get("score", 0),
        reverse=True,
    )
    return ScanOutcome(
        results=results,
        universe_result=universe_result,
        discovery_result=discovery_result,
        scan_seconds=perf_counter() - started,
    )
