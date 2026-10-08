# Phase 3.2 — Completed-bar structural research setup

Status: initial pure calculation and tests published on development;
**not yet validated on the user's Windows machine**.

The pure module `tradepilot/technical_setup.py` derives future long breakout
levels from a supplied, chronological OHLCV DataFrame. The caller MUST supply
only completed, appropriately adjusted bars. The function cannot independently
prove completion, adjustment, timestamp provenance or provider freshness.

- Resistance: highest High of last 20 completed bars.
- Support: lowest Low of last 20 completed bars.
- Structural stop: lowest Low of last 10 completed bars minus 0.1%.
- Future entry trigger: resistance plus 0.1%.
- Research target: entry plus twice the gross entry-to-stop distance.
- Phase 3.1 then evaluates net fees/slippage, risk and sizing.
- This is a deterministic **hypothesis**, not a validated trading strategy.
- No real breakout confirmation, live quote verification, broker instrument
  verification or order execution. Every proposal is `WAIT` and
  `actionable=False`, even if structural levels can be computed.
- Missing/invalid OHLCV, insufficient bars and out-of-order data fail closed.
- No DB writes, UI, scheduler or watchlist state changes.

Validate:
```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
git switch development
git pull origin development
.\.venv\Scripts\python.exe -m py_compile tradepilot\technical_setup.py tests\test_technical_setup.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Expected 161 tests (149 prior + 12 new), subject to local confirmation.

Next: validate completed-bar provenance and adjusted prices, expose a
read-only watchlist setup preview, model trigger/expiry without look-ahead,
and test historical strategy behavior before any actionable state.
