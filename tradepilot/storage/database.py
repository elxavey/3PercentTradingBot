"""SQLite foundation for TradePilot (schema v1).

This module does not start jobs, fetch market data, or place orders.
All timestamps supplied by callers should be UTC ISO-8601 strings.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB_PATH = Path("data") / "tradepilot.db"
SCHEMA_VERSION = 1

_MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS job_runs (
    id TEXT PRIMARY KEY,
    job_name TEXT NOT NULL,
    scheduled_for_utc TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    finished_at_utc TEXT,
    status TEXT NOT NULL CHECK(status IN
        ('RUNNING','SUCCEEDED','FAILED','INTERRUPTED','SKIPPED')),
    config_version TEXT NOT NULL,
    error_message TEXT,
    UNIQUE(job_name, scheduled_for_utc)
);

CREATE TABLE IF NOT EXISTS scan_runs (
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

CREATE TABLE IF NOT EXISTS scan_candidates (
    scan_run_id TEXT NOT NULL REFERENCES scan_runs(id),
    symbol TEXT NOT NULL,
    exchange_code TEXT,
    currency TEXT,
    quality_pass INTEGER NOT NULL CHECK(quality_pass IN (0,1)),
    opportunity_score REAL,
    legacy_score REAL,
    observed_at_utc TEXT NOT NULL,
    price_source TEXT,
    price REAL,
    raw_result_json TEXT NOT NULL,
    PRIMARY KEY(scan_run_id, symbol)
);

CREATE TABLE IF NOT EXISTS watchlist_entries (
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    state TEXT NOT NULL,
    first_seen_at_utc TEXT NOT NULL,
    last_seen_at_utc TEXT NOT NULL,
    last_scan_run_id TEXT REFERENCES scan_runs(id),
    PRIMARY KEY(symbol, market)
);

CREATE TABLE IF NOT EXISTS market_data_observations (
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

CREATE INDEX IF NOT EXISTS idx_scan_candidates_rank
    ON scan_candidates(scan_run_id, quality_pass, opportunity_score DESC);
CREATE INDEX IF NOT EXISTS idx_market_data_latest
    ON market_data_observations(symbol, interval, bar_end_utc DESC);
"""


def connect_database(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a configured connection. Caller owns and closes it."""
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=10)
    try:
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            connection.execute("PRAGMA journal_mode = WAL")
        return connection
    except BaseException:
        connection.close()
        raise


def initialize_database(db_path: str | Path = DEFAULT_DB_PATH) -> int:
    """Create/upgrade database and return schema version.

    Migration is transactional and safe to invoke multiple times.
    """
    connection = connect_database(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, applied_at_utc TEXT NOT NULL)"
        )
        current = connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
        ).fetchone()[0]
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema {current} is newer than supported {SCHEMA_VERSION}"
            )
        if current < 1:
            # executescript commits implicit transactions: use individual statements
            # so the migration and version record remain atomic.
            for statement in _MIGRATION_1.split(";"):
                if statement.strip():
                    connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at_utc) "
                "VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"
            )
        connection.commit()
        return SCHEMA_VERSION
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


@contextmanager
def database_connection(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> Iterator[sqlite3.Connection]:
    """Transaction scope: commit on success, rollback on exception, always close."""
    connection = connect_database(db_path)
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
