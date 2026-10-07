# TradePilot — Phase 0 Technical Audit and Phase 1 Specification
Date: 2026-10-07 | Source branch: development | Baseline: v0.4.0
Status: Phase 0 design deliverable; no runtime changes in this commit.

## 1. Audited source files
- `app.py` (331 lines): Streamlit directly coordinates universe discovery, pre-screen and stock scoring; background worker is absent.
- `screener.py` (127 lines): reusable `score_stock`, but fetches fundamentals internally, mixes data acquisition and rule evaluation; `price` prefers 24-hour cached metadata `currentPrice` over latest OHLCV close.
- `data_fetcher.py` (139 lines): JSON fundamentals cache read on every symbol and fully rewritten on misses; 24-hour TTL. Historical cache per-symbol CSV, 6-hour TTL; CSV cache key ignores `period`; no intraday freshness contract.
- `universe_manager.py` (69 lines): sequential per-ticker OHLCV fetch and pre-screen; universal 5,000,000 traded-value threshold regardless of currency, whereas Quality Gate has market-specific thresholds.
- `universe_discovery.py` (78 lines): Yahoo screener pagination; no explicit retries/backoff on provider failures; MX target 20% but 1,000-run found only 62 MX.
- `technical_rules.py` (406 lines), `fundamental_rules.py` (113 lines): reusable indicators and checks; ensure indicator inputs are point-in-time for future backtesting.
- `config.py`: v0.4.0 and threshold definitions; `requirements.txt`: unpinned dependencies; `.gitignore`: .cache excluded; `main.py`: legacy CLI.
- `docs/PROJECT_ROADMAP.md`: approved scope includes GBM manual recommendations and separate paper trading.
Audit based on repository code inspection; **no local Windows run or automated test execution performed**.

## 2. Design constraints
- Keep existing `app.py` UI and scanner behavior stable until tested.
- No real-money broker connection, automatic order submission, GBM credentials, or live trading in Phase 1.
- One local SQLite DB with WAL mode, busy timeout and short write transactions; single background worker writes, Streamlit reads.
- UTC timestamps for storage, exchange-local times for display; market-specific calendars.
- Do not equate a cached Yahoo metadata price with a fresh tradable quote.
- Treat Yahoo data as research-grade until latency, coverage and provider rights are verified.

## 3. Proposed module layout (incremental, not a rewrite)
```
app.py                       # Streamlit UI, read persisted run results
screener.py                  # existing compatibility entry points
data_fetcher.py              # existing compatibility entry points
tradepilot/
  __init__.py
  core/
    models.py                # immutable market bars, signals, run statuses
    scanner_service.py       # scanner orchestration, independent of UI
    market_data.py           # provider interface + freshness policy
  storage/
    database.py              # sqlite connect/migrations/transactions
    repositories.py          # runs, watchlist, bars, signals, jobs
  scheduling/
    worker.py                # background process main entry
    jobs.py                  # daily scan, watchlist refresh, EOD
    calendars.py             # MX/US session handling
  monitoring/
    health.py                # freshness, job status, error reporting
tests/
  test_database.py
  test_scanner_service.py
  test_data_freshness.py
  test_scheduler_idempotency.py
```
Trade Setup, Backtesting, GBM and Paper Trading modules will be added in later phases, **not** as empty implementations now.

## 4. Initial SQLite schema proposal
```sql
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at_utc TEXT NOT NULL
);
CREATE TABLE job_runs (
    id TEXT PRIMARY KEY,
    job_name TEXT NOT NULL,
    scheduled_for_utc TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    finished_at_utc TEXT,
    status TEXT NOT NULL CHECK(status IN ('RUNNING','SUCCEEDED','FAILED','INTERRUPTED','SKIPPED')),
    config_version TEXT NOT NULL,
    error_message TEXT,
    UNIQUE(job_name, scheduled_for_utc)
);
CREATE TABLE scan_runs (
    id TEXT PRIMARY KEY,
    job_run_id TEXT REFERENCES job_runs(id),
    universe_name TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    finished_at_utc TEXT,
    status TEXT NOT NULL,
    discovered_count INTEGER,
    pre_screen_count INTEGER,
    quality_pass_count INTEGER,
    elapsed_seconds REAL,
    config_snapshot_json TEXT NOT NULL
);
CREATE TABLE scan_candidates (
    scan_run_id TEXT NOT NULL REFERENCES scan_runs(id),
    symbol TEXT NOT NULL,
    exchange_code TEXT,
    currency TEXT,
    quality_pass INTEGER NOT NULL,
    opportunity_score REAL,
    legacy_score REAL,
    observed_at_utc TEXT NOT NULL,
    price_source TEXT,
    price REAL,
    raw_result_json TEXT NOT NULL,
    PRIMARY KEY(scan_run_id, symbol)
);
CREATE TABLE watchlist_entries (
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    state TEXT NOT NULL,
    first_seen_at_utc TEXT NOT NULL,
    last_seen_at_utc TEXT NOT NULL,
    last_scan_run_id TEXT,
    PRIMARY KEY(symbol, market)
);
CREATE TABLE market_data_observations (
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    bar_end_utc TEXT NOT NULL,
    source TEXT NOT NULL,
    fetched_at_utc TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL,
    PRIMARY KEY(symbol, interval, bar_end_utc, source)
);
CREATE INDEX idx_scan_candidates_rank
    ON scan_candidates(scan_run_id, quality_pass, opportunity_score DESC);
CREATE INDEX idx_market_data_latest
    ON market_data_observations(symbol, interval, bar_end_utc DESC);
```
No paper/GBM real-trade tables in Phase 1; design those after trade lifecycle and accounting contracts are specified. Do not store secrets in SQLite.

## 5. Data and service contracts
- `MarketObservation`: symbol, market, currency, interval, OHLCV, bar_end_utc, fetched_at_utc, source, adjusted flag, session state.
- `ScanRequest`: universe mode, target size, rule config snapshot, requested_at_utc, unique job ID.
- `ScanResult`: run ID, timestamps, status, discovered/pre-screen/quality counts, candidates, cache telemetry, errors.
- `FreshnessAssessment`: FRESH / STALE / UNKNOWN with age, interval, exchange session and reason; only FRESH inputs can produce future actionable intraday signals.
- `JobRun`: scheduled key, start/end, status, errors, retry count. Never assume that a missed run executed while Windows was sleeping.
- `MarketDataProvider`: `get_daily_history(symbol,...)`, `get_intraday_bars(symbol, interval,...)`, `get_quote(symbol,...)`; return source/time metadata, not bare price. Missing unsupported quote data must be explicit.
- `ScannerService`: pure-ish orchestration using injected provider/storage, returning results without Streamlit imports. Keep `score_stock` backward compatible during transition.

## 6. Job schedule design (initial proposal, to be validated)
- Market calendar per exchange, daylight-saving aware; do not hardcode 06:30.
- Daily broad scan using completed daily bars, prior to each market's open when provider permits.
- After opening +15m: shortlist update; every 5m completed-bar shortlist refresh; every 15m more expensive setup later.
- After close: daily snapshot and telemetry.
- Singleton worker, database unique job key, restart reconciliation, paused flag, no duplicate executions.
- UI must not instantiate scheduler; Windows Task Scheduler can launch worker on login/startup.
- A full 1,000 scan previously took 858.8s; no guarantee of 10-minute run or realtime intraday capability.

## 7. Acceptance tests for Phase 1
1. Existing 12/62/250 scanner modes retain comparable ranking and counts on the **same frozen data snapshot**.
2. Background worker can complete a scan while Streamlit is closed; UI later reads persisted results.
3. Closing/reopening UI does not reset DB, job state or cached results.
4. Restart during scan records interruption; no duplicate job or fabricated completion.
5. Market holidays and timezone/DST transitions skip invalid jobs.
6. Failed provider request yields recorded error and stale/unknown status, never actionable BUY.
7. Cache keys distinguish symbol/interval/period/adjustment; metadata cache is not used as a fresh quote.
8. SQLite migration and write/read tests run in isolated temporary DBs.
9. Worker/Streamlit concurrent read/write smoke test succeeds under WAL.
10. No real-money order integration or secrets added.

## 8. Implementation sequence after approval
1. Add `tradepilot/storage/database.py` and versioned migration, plus tests.
2. Add models and data freshness contract/tests; preserve existing fetcher API.
3. Extract scanner orchestration into `scanner_service.py`; verify old UI equivalence.
4. Add worker + scheduler + calendar + restart/idempotency tests.
5. Add read-only UI for run history, last successful scan, stale flags and worker health.
6. Profile hot/cold caches and optimize metadata persistence in controlled steps.

## 9. Known open questions
- Select dependable intraday provider and validate data licensing/latency for MX/US; Yahoo alone may be insufficient for actionable GBM suggestions.
- Confirm exact GBM account instrument access, order types, commissions and currency conversion before GBM Recommendation phase.
- Choose precise trade/stop/cost rules only after research, not by assumption.
- Clarify whether a 1–5-session trade may carry through earnings releases; consider event-risk guard.
- Determine baseline benchmark and out-of-sample periods for backtest.

## 10. Next developer action
Proceed with Phase 1 step 1 (SQLite migration and unit tests) as a **separate small commit** on `development`. Do not alter `master`, rename repo or activate paper/real orders.
