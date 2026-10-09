# TradePilot morning radar — implementation plan (not enabled)

## Architecture
- Windows Task Scheduler launches a **separate Python CLI**, not Streamlit, while the user's PC is on. Streamlit only reads persisted scan results.
- Schedule a short polling task on market weekdays; the CLI checks **exchange_calendars** (XMEX and XNYS) for the actual open, half-days, holidays, and daylight-saving transitions. Run each market **once per exchange session**, at the first polling tick at least 30 minutes after its opening; persist an idempotency key `market:session:morning` in SQLite.
- Scan a **market-specific** universe, with explicit provider call budgeting, bounded concurrency, caching, retries, per-symbol failures, scan-completeness counts, and last successful run metadata. No EODHD calls without explicit opt-in.
- At +30 minutes, current completed daily bars are **prior-session EOD**. Do not call this live or intraday-confirmed. A true opening radar requires separately sourced, timestamped intraday quotes and volume with market-data licensing/coverage and proper partial-session RVOL normalization.
- Morning email: label `prior close / as of`, market, session, provider freshness, candidate state, score (heuristic), close, trigger, volume, exclusions, scan coverage, and link/instructions to open local Streamlit. If incomplete scan, warn prominently rather than presenting a definitive universe-wide top 10.
- Gmail: use a dedicated account or approved OAuth 2.0 flow, or Google app password **only if account supports it**, via environment variables / Windows Credential Manager. Never commit credentials, tokens, recipients, or .env files. Use SMTP TLS with certificate validation; send a **test message** only after explicit setup/approval. Deduplicate email by market/session and record success/failure; failed sends can retry without rerunning market scans.
- Add task installer script only after CLI is tested. Task runs with user's Windows identity, correct working directory and venv Python, starts if missed, and logs to local rotating logs. Windows PC must be awake and connected; sleep/hibernation prevents timely execution.
- Keep `development` as the only implementation branch; do not change `master`.

## Delivery sequence
1. Streamlit Breakout Radar (implemented in `pages/1_Breakout_Radar.py`), read-only existing JSON + optional manual scan for 20/62 static equities.
2. Persisted per-market scan runner with tested exchange-open clock and idempotency, offline fixtures.
3. Universe-wide scalability/coverage and provider-rate-limit tests before enabling dynamic 250/500/1000.
4. Gmail opt-in HTML sender with dry-run, recipient validation, credential isolation, retry tests.
5. Windows Task Scheduler installer, end-to-end dry run, then explicit enablement.

**No automatic task or email has been enabled by this document.**
