# 3% Trading Bot — Objectives, Architecture & Development Plan
Status: APPROVED PROJECT SCOPE (design only) | Baseline code: v0.4.0 | Updated: 2026-10-07

## 1. Mission
Build a personal Windows-based, automated **short-swing (1–5 trading sessions)** opportunity system covering **Mexico and USA**, with two independent paths using the same validated trade-setup and risk rules:
1. **Automatic paper trading**: simulate orders, fills, exits, portfolio and costs; never send live orders.
2. **GBM Manual Trading Assistant**: suggest *potential* GBM-compatible trades with entry, order type, target, stop, quantity, net cost/FX estimates, expiry, rationale and warnings. The user places any real orders manually in GBM; no GBM credentials or broker order integration in v1.

The ~3% **net** per successful trade is a research target, **not a guaranteed return**, daily quota, or automatic buy instruction. Test an initial +3.6% gross target only as a hypothesis; costs and exchange rates may change the required target.

## 2. Fixed product decisions
- Holding period: 1–5 **market sessions**, with explicit time-exit policy to be tested.
- Markets: MX and US, distinct calendars, sessions, currencies, liquidity and instrument mappings.
- Autonomy: automated **paper** trading; manual-only GBM execution.
- Host: user's Windows PC; Python, Streamlit dashboard, background worker, SQLite, GitHub development branch.
- Personal/internal use; pragmatic modular monolith, not microservices.
- Keep master stable; small commits to development, user tests on Windows before merge.

## 3. Existing baseline (v0.4.0)
- Dynamic Yahoo Finance universe (250/500/1,000 symbols), pre-screen, Quality Gate, Opportunity Score, historical/fundamental file caches, timing telemetry, CSV exports.
- Latest observed 1,000-symbol run: discovery 1,000 (62 MX, 938 US); pre-screen 949; Quality Gate 835; 858.8 s total. These are observed benchmark figures, not guaranteed throughput.
- Opportunity Score is **a ranking heuristic, not a calibrated probability or purchase signal**.
- No reliable intraday feed, scheduler, operational DB, trade setup, validated backtest, portfolio risk, paper fills, GBM compatibility or live broker integration yet.

## 4. Target architecture (single Python project)
1. **Market Data / Quality** — daily + intraday OHLCV, provider abstraction, cache with freshness and timestamps, retries/rate limits, FX, trading calendars, split/dividend adjustments, stale-data fail-closed.
2. **Market Scanner** — discovery -> pre-screen -> Quality Gate -> Opportunity Score. Preserve and refactor current code.
3. **Dynamic Watchlist** — shortlist (initial target 20–50), periodic refresh, promotion/removal, deduplication.
4. **Trade Setup** — market structure (support/resistance), entry validation, order plan, target/stop, reward/risk, expiry, explanations.
5. **Signal / State Engine** — DISCOVERED -> WATCHING -> READY/WAIT/REJECT -> OPEN -> CLOSED/EXPIRED; deterministic decisions, idempotent events.
6. **Portfolio Risk** — per-trade risk, max open positions, correlated exposure, capital allocation, daily limits, market/FX constraints.
7. **Backtesting / Research** — historical signal replay without look-ahead, realistic fill assumptions, intrabar ambiguity, spreads/slippage/fees, FX, survivorship caveats, out-of-sample evaluation and baselines.
8. **Paper Trading** — virtual cash and orders, simulated fills, stop/target/time exits, recovery, performance and ledger.
9. **GBM Trade Recommendations** — rank *validated* setups, verify tradability and instrument identity (MX listing/SIC/US access), show GBM-relevant limit/other supported order type, entry range, target, stop, quantity, estimated costs, FX, recommendation expiry and status. **Never claim GBM support without verified mapping and order capability**.
10. **My GBM Portfolio** — manually entered/confirmed real executions, actual fill price/quantity/fees, tracked separately from simulated positions; no assumptions that a recommendation was filled.
11. **Scheduler / Recovery / Alerts** — Windows startup, market-aware job schedules, singleton lock, restart/resume, failed-run logging, deduped alerts, pause/kill switch.
12. **Streamlit Dashboard / Journal** — read-only overview plus explicit controls, watchlist, trade suggestions, simulated and manual portfolios, decision audit, CSV exports.

Share **one pure decision/risk core** among scanner, backtest, paper trader and GBM recommendation path; no strategy rules duplicated inside UI.

## 5. Proposed operating cadence (to validate with real data and provider constraints)
- Before each exchange opens: refresh broad universe and daily ranking using available completed bars.
- ~15 minutes after opening: first intraday setup validation; avoid immediate opening noise.
- Every ~5 minutes: refresh shortlist (initially top 20) on **completed bars**, subject to provider freshness.
- Every ~15 minutes: recompute more expensive structure/setup for shortlist.
- Every ~1 minute: **simulated** position oversight; no promise of executable stop prices or minute-level data availability.
- Mid-session: optional broad refresh if cost/latency allows; after close: persist data, journal, metrics.
- No trading on exchange holidays; US and MX schedules are independent and DST-aware.
- Windows sleep/offline means no monitoring. Recovery logs gaps and reconciles simulated state; it must not fabricate fills.

## 6. GBM recommendation contract (no live orders)
Each suggestion must contain:
- Symbol + **verified GBM instrument/market** and currency; if unverified: NOT ACTIONABLE.
- Quote timestamp, source, session, freshness, last/reference price and bid/ask when available.
- Signal ID, score, setup reason, entry trigger and **limit price/range**, recommended order type *only if supported*, time-in-force/expiry.
- Target price, structural stop, expected gross/net % after configurable fees/taxes/spread/slippage/FX; risk/reward.
- Proposed quantity based on **available budget** and per-trade risk, with lot/whole-share constraints and cash left.
- State: READY / WAIT / REJECT / STALE / EXPIRED; reason for state changes.
- Manual GBM checklist and optional user-confirmed executed trade for My GBM Portfolio.
- If current executable price deviates from proposed entry, invalidate/recalculate; do not chase.
- Recommendations are research assistance, **not automated orders** or guaranteed gains.

## 7. Initial strategy assumptions (all configurable, subject to backtesting)
- Paper portfolio: MXN 10,000.
- Gross target candidate: +3.6%; structural stop with -1.8% only as illustrative reference.
- Risk per trade: 0.5% of total equity (illustrative); max 3 concurrent positions (illustrative).
- Holding horizon: 1–5 sessions; enforce expiry.
- Require positive estimated net expectancy and adequate reward/risk **based on out-of-sample evidence**, not arbitrary scores.
- Realistic constraints: fractional/whole shares, market-specific lot sizes, trading fees, taxes, FX and spreads. Never assume all Yahoo US tickers are GBM-tradable.

## 8. Development roadmap and acceptance gates
**Phase 0 — Repo audit / design freeze (no strategy behavior changes)**
- Inspect existing modules, data-fetch signatures, cache, performance bottlenecks, dependencies and tests.
- Deliver module boundaries, SQLite schema, configuration and data contracts, failure policies, acceptance tests.
- Gate: design reviewed; v0.4.0 behavior reproducible.

**Phase 1 — Foundation / data / orchestration**
- Decouple Streamlit from computation; SQLite persistence, job scheduler, market calendars, data timestamps, intraday provider abstraction, cache optimization, singleton jobs and restart recovery.
- Gate: scheduled scan runs with UI closed, durable result, no duplicate jobs, fail-closed on stale data, Windows restart recovery demonstrated.

**Phase 2 — Dynamic watchlist**
- Top 20–50 with promotion/expiry, incremental data refresh, observability.
- Gate: watchlist updates on schedule without reprocessing 1,000 symbols each time.

**Phase 3 — Trade Setup + Risk + Signal**
- Market structure, entry trigger, stop/target, net cost, position sizing, states and reasons.
- Gate: deterministic unit tests, reproducible explanations and no BUY CANDIDATE without valid risk/data checks.

**Phase 4 — Backtesting / strategy validation**
- Replay identical pure decision functions with point-in-time data, simulated fills, fees/FX and out-of-sample tests.
- Gate: reproducible reports, bias checks, baseline comparisons; no claims of edge without evidence.

**Phase 5 — GBM Recommendations + manual portfolio**
- Verified instrument mapping, actionable recommendation card, alerts, expiry, manual entry journal, separate real/manual ledger.
- Gate: cannot label unverified instruments/orders as GBM-actionable; manual execution never triggered by app.

**Phase 6 — Automatic paper trading**
- Simulated order lifecycle, portfolio constraints, 1–5-session exits, persistence and performance metrics.
- Gate: multi-session unattended simulation with correct restarts, fills and no duplicated trades.

**Phase 7 — Operational dashboard / hardening**
- Metrics, alerts, pause switch, daily reports, reliability and sustained paper-trading observation.
- Gate: stable Windows operation, auditable decisions, known data gaps and realistic net performance.

**Future / explicitly out of v1 scope:** automatic real-money GBM or IBKR order placement, guaranteed 3% profits, paid institutional data by default, cloud hosting and multi-user access.

## 9. Engineering rules
- Never use future candles or today’s final volume in historical intraday signals; no look-ahead.
- Backtest delisted instruments where historical universe data permits; report survivorship limits when it does not.
- Cache expiration is not deletion; measure warm vs cold runs. Validate live quote freshness separately from metadata TTL.
- On ambiguous same-bar stop/target hits, use documented conservative assumption or higher-resolution data.
- Persist timestamps in UTC plus exchange timezone, job IDs, signal IDs, versions and full decision reasons.
- Keep paper and real/manual ledgers segregated; distinguish recommendations, submitted orders and confirmed fills.
- Broker compatibility, fees, FX and order-type support are **unknown until verified**.
- Each phase ships as small commits to development; user tests Build/Run locally before merge to master.

## 10. Next action
Start **Phase 0**: inspect repository on `development`, produce a concrete Phase 1 technical specification (folder layout, SQLite DDL, job contracts, provider interfaces, tests), then implement in small commits **only after approval**.
