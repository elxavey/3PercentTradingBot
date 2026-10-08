# Phase 4.3 — Backtest Runner and Performance Metrics

Research-only integration: `tradepilot.backtest_runner.run_backtest(history, symbol="ALSEA.MX", market="MX")`.

Inputs: **completed, validated exchange-session daily OHLCV**, ascending unique DatetimeIndex. This module does not download data, authenticate corporate/broker data, write SQLite, or place orders.

Pipeline:
1. `replay_signals` evaluates only bars known at each historical close.
2. `simulate_trades` enters no earlier than the next session's open, assumes one long position per symbol, uses conservative stop-first ambiguity, applies configured per-side fee/slippage, and excludes unclosed final positions.
3. `performance_metrics` summarizes closed trades only: win rate, mean net return, mean wins/losses, average holding sessions, profit factor (undefined if no losses), hypothetical compounded sequential return and **closed-trade-only** drawdown.

**Interpretation:** compounded return assumes reinvestment of all capital in sequential trades; it is not a portfolio result. Closed-trade drawdown ignores unrealized/intratrade drawdowns. Metrics cannot be pooled across MXN and USD without verified historical FX. The simulator has no spread/liquidity, tax, capital allocation or out-of-sample model. Current universe may have survivorship bias; data provenance, adjusted prices, corporate actions and delisted symbols must be verified. Zero closed trades gives null/undefined metrics, not a claim of 0% success.

Default research hypothesis: +3.6% gross target, -1.8% stop, five-session exit, fee and slippage defaults zero **for isolated tests only**. Before evaluating profitability set realistic fees and slippage and validate OHLCV completeness. The 3% net objective is not guaranteed.

Next gates: historical input integrity/calendar validation, realistic costs and FX, out-of-sample evaluation, baseline comparison and portfolio-aware drawdown. No production trading.
