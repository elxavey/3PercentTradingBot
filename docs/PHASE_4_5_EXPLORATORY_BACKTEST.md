# Phase 4.5 — Exploratory historical backtests

The CLI now defaults to exploratory research mode. A complete history runs normally.
Up to two **isolated** missing exchange sessions are allowed; the result is marked
`PARTIAL_HISTORY`. Three missing sessions, consecutive missing sessions, malformed
OHLCV, or insufficient history still cause rejection.

A gap divides the price series into independent continuous exchange-session
segments. Signals, lookbacks, entries and exits never cross a missing session.
Segments shorter than 100 bars are excluded, and open trades at segment ends are
not counted as closed trades. Reported metrics therefore describe only the
eligible segments; they are not a complete-history performance estimate.
No missing bar is synthesized. No backfill is attempted in exploratory mode.

The `--strict` option restores strict validation and attempts Yahoo one-day
recovery. EODHD is **never queried by default** even when a token is present.
`--use-eodhd` explicitly permits provider recovery, including in exploratory
mode, and `--diagnose-eodhd` requires that opt-in.

Examples:

```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
.\.venv\Scripts\python.exe -m tradepilot.backtest_cli --symbol ALSEA.MX --market MX --fee 0.0025 --slippage 0.001
.\.venv\Scripts\python.exe -m tradepilot.backtest_cli --symbol ALSEA.MX --market MX --fee 0.0025 --slippage 0.001 --strict
```

This is research only. The approach avoids fictitious executions through data
gaps but can exclude genuine signals and trades. The count of excluded signals
or trades cannot be known without the missing bars; do not interpret excluded
segments as exact excluded-trade counts.
