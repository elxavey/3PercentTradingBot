# Phase 3.5 — Opportunity Monitor

Branch: `development`. Research-only, no live alerts, broker orders, database migration, or Windows scheduler modifications.

## Workflow
Open Streamlit page **Opportunity Monitor** and click **Refresh opportunity monitor**. Each active WATCHING/PROMOTED watchlist symbol is fetched on explicit request and filtered to completed exchange-calendar sessions using the existing Phase 3.3 adapter. If latest completed session is missing or data cannot be validated, the symbol is `INSUFFICIENT_DATA`.

For each completed session, compare its closing price to the highest High of the **20 previous completed sessions**. The observation itself is **not** included in resistance, preventing a self-referential breakout threshold. Distance % = (prior resistance - completed close) / prior resistance * 100.

- `BREAKOUT_CANDIDATE`: latest completed close is strictly above prior resistance. **Not a confirmed executable breakout.**
- `APPROACHING`: completed close is at or below resistance and within user-defined 0.5–10% proximity (default 3%).
- `MONITORING`: below that proximity threshold.
- `INSUFFICIENT_DATA`: missing, invalid or stale completed historical data.

Historical proximity is **reconstructed on demand** from rolling completed candles, using only data available through each observation. It is not a persisted daily audit trail; it is not proof of what the system knew at that historical time. No automatic alerts are sent.

## Validation (Windows PowerShell)

```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
git switch development
git pull origin development
.\.venv\Scripts\python.exe -m py_compile tradepilot\opportunity_monitor.py pages\5_Opportunity_Monitor.py tests\test_opportunity_monitor.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Expected tests: 182 if baseline was 173; must be verified locally. Existing scanner and watchlist scheduled tasks remain unchanged.
