# TradePilot — Phase 2.2: Watchlist lifecycle (first increment)

Implemented in **development** only. This is a **research workflow**, not
an order execution or trading recommendation engine.

## Behavior

- **WATCHING**: a Quality Gate PASS candidate with Opportunity Score below 70.
- **PROMOTED**: a Quality Gate PASS candidate with Opportunity Score **70 or
  above**. This is a configurable future research threshold, **not** a
  predicted 70% probability, buy signal or profit guarantee.
- A subsequent, explicitly applied newer scan can move an active symbol
  between WATCHING and PROMOTED based on its new saved score.
- **EXPIRED**: manual retirement, confirmed in the UI.
- **REMOVED**: manual retirement, confirmed in the UI.
- EXPIRED and REMOVED are terminal in this increment; a later scan **cannot
  silently reactivate** them.
- Each new observation/transition records a watchlist audit event with
  previous and new states, previous and new scores, scan ID and UTC timestamp.
  Reapplying the same scan does not add duplicate events.
- Existing watchlist rows are **preserved** by schema migration v4. Rows
  created before v4 do not have retrospective events; their next genuinely
  newer scan creates the first new event.
- Missing symbols in a scan are retained: no automatic expiration based on
  absence, as an absent symbol may simply be outside that scan's universe.
- **Session-based expiry is now available as an explicit reviewed action**
  in Watchlist, using a selected successful saved scan. The preview requires
  **three consecutive open sessions** in the symbol's own XNYS/XMEX calendar,
  with an actual candidate row and Quality Gate FAIL (`quality_pass=0`)
  for that symbol on each session, all from the **same universe** and
  strictly newer than its last watchlist observation.
- An absent symbol, a missing exchange session, a Quality Gate PASS,
  or a scan of a different universe **cannot count as a failed session**.
  The selected scan itself must contain the failing candidate. Multiple
  evaluations on one day count as one session. The preview never writes.
- Clicking **Apply session expiry** after checking the confirmation box
  changes eligible entries to EXPIRED and creates an audit event with reason
  `AUTO_QUALITY_FAIL_3_SESSIONS`. Repeating it does not add duplicate events.
- This is **not unattended automatic expiry**: the Windows worker and scanner
  do not mutate watchlist states. A fully automated expiry job would require
  a separate opt-in and additional operational validation.

## Validate on Windows

Close the Streamlit server before updating the code if it is holding an
old import; do not delete SQLite files.

```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
git switch development
git pull origin development
.\.venv\Scripts\python.exe -m py_compile tradepilot\watchlist.py tradepilot\storage\database.py pages\2_Watchlist.py tests\test_watchlist_lifecycle.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Expected **119 tests** (previous 113 plus 6 new expiry tests).

```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

In Watchlist, check the lifecycle status and choose a symbol to inspect
the history. **Do not click Confirm retirement yet** unless you want that
symbol irreversibly excluded from future promotions. For score-change
history, apply a **newer** completed scan; do not fabricate a scan.

The scheduler and scanner are unchanged. Windows scheduled market-window
execution is still awaiting empirical validation.
