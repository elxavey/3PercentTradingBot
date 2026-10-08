# Phase 4.6 — Multi-symbol historical research comparator

Run the same fixed simulation policy over multiple tickers (up to 62).
The comparator reuses the existing Phase 4.5 exploratory or Phase 4.4 strict
validation and simulation. It is **research-only**, read-only, and never
places broker orders or queries EODHD. Yahoo price-history cache is reused
when fresh; stale/missing cache may trigger normal Yahoo history downloads.

Start with up to 12 active symbols in the local watchlist:

```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
.\.venv\Scripts\python.exe -m tradepilot.backtest_compare_cli --watchlist --limit 12 --fee 0.0025 --slippage 0.001
```

Or supply an explicit set (no need to have a populated watchlist):

```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
.\.venv\Scripts\python.exe -m tradepilot.backtest_compare_cli --symbols ALSEA.MX WALMEX.MX AAPL MSFT --fee 0.0025 --slippage 0.001
```

Add `--strict` to reject any remaining missing exchange sessions; the
comparator intentionally does **not** attempt recovery in either mode.
If any symbol is rejected or fails, its row remains visible and the process
exits with code 2. Valid rows still appear. Individual fetch/validation
failures do not interrupt the other symbols.

`results` retains each symbol's status, missing sessions, validation mode,
signal count, closed trades, win rate, average net return, hypothetical
compounded return, closed-trade drawdown and profit factor. `ranking`
sorts only symbols with **at least 10 closed trades** by average net
return per trade (descending). Fewer trades are reported but not ranked.
This threshold is a reporting guardrail, not statistical significance.

The ranking does not constitute a buy recommendation, portfolio return,
out-of-sample evaluation or statistically robust proof of profitability.
US and MX trade returns are percentages, not converted to a common
currency. Do not combine hypothetical compounded returns across symbols.
