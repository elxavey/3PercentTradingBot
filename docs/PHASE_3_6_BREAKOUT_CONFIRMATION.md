# Phase 3.6 — Breakout Confirmation

Implemented only on `development`. Read-only, manual, historical research.

## Definition

The monitor adds **historical confirmation** to Phase 3.5's independent proximity status. Filters require all three:

1. **Persistence:** 2 completed daily closes (configurable 2–4) strictly above the same resistance formed by the prior 20 completed sessions **before** the persistence window, plus a 0.1% buffer (configurable 0–3%).
2. **Volume:** latest completed day's volume >= 1.2 times the average volume of the 20 completed days **before** the persistence window (configurable 1–3).
3. **Trend:** latest completed close above the previous 20-session SMA, and that SMA greater than the first close in its baseline window. This is a simple directional filter, not an established trading signal.

`HISTORICAL_FILTERS_PASSED` means historical evidence only; it is **not** an executable or real-time breakout. `FILTERS_NOT_MET` lists failing checks. Missing/invalid OHLCV or zero baseline volume fail closed. Phase 3.5's existing state is preserved and shown alongside confirmation.

Current session is excluded using existing exchange calendars; stale or unverifiable history remains `INSUFFICIENT_DATA`. No live price, corporate-action adjustment verification, actual bid/ask, fees, FX, or broker confirmation. No backtest or profitability claim. No SQLite writes, alerts, scheduler changes or GBM integration.

## Windows validation

```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
git switch development
git pull origin development
.\.venv\Scripts\python.exe -m py_compile tradepilot\breakout_confirmation.py pages\5_Opportunity_Monitor.py tests\test_breakout_confirmation.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Expected total: 192 tests if baseline was 182; verify locally. Open **Opportunity Monitor**, adjust filters and click **Refresh opportunity monitor**.
