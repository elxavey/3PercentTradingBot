# Phase 4.7 — Stop sensitivity and risk control

Research-only, never places orders or modifies the default 1.8% stop.
Compares fixed 1.8%, 2.5%, 3.0% stops using the same 3.6% gross
target, five-session holding limit, and explicit costs. Each symbol's
Yahoo history is fetched only once for all three scenarios. No EODHD.

Read-only latest completed SQLite scan universe, up to 62 symbols:

```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
git switch development
git pull origin development
.\.venv\Scripts\python.exe -m unittest tests.test_risk_optimization_cli
.\.venv\Scripts\python.exe -m tradepilot.risk_optimization_cli --universe --limit 62 --capital 10000 --risk-pct 1 --fee 0.0025 --slippage 0.001
```

Start with active watchlist instead:

```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
.\.venv\Scripts\python.exe -m tradepilot.risk_optimization_cli --watchlist --limit 12 --capital 10000 --risk-pct 1 --fee 0.0025 --slippage 0.001
```

`--strict` requires complete exchange-session history. The default
exploratory mode splits isolated gaps without fabricating candles.
Rejected histories and provider errors remain visible in results.

The risk budget is a **planned stop-loss estimate**, not a guaranteed
loss cap. Overnight gaps, liquidity, commissions and execution can cause
greater losses. Capital is MXN for sizing examples; US instruments
require FX conversion before applying the same cash budget. No
portfolio backtest or out-of-sample validation is performed.
Aggregated per-trade averages are not portfolio returns.

The program deliberately does not choose an optimal stop, change the
strategy defaults, submit orders, or claim profitability.
