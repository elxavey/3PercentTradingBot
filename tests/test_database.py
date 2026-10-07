"""Phase 1.1 SQLite Foundation tests; stdlib unittest, no external packages."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tradepilot.storage.database import (
    SCHEMA_VERSION,
    connect_database,
    database_connection,
    initialize_database,
)


class DatabaseFoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "nested" / "tradepilot.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_initialize_creates_database_and_schema(self):
        self.assertEqual(initialize_database(self.db), SCHEMA_VERSION)
        self.assertTrue(self.db.exists())
        with database_connection(self.db) as conn:
            names = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            self.assertTrue({
                "schema_migrations", "job_runs", "scan_runs",
                "scan_candidates", "watchlist_entries",
                "market_data_observations"
            }.issubset(names))
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM schema_migrations"
            ).fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_initialize_twice_does_not_repeat_migration(self):
        initialize_database(self.db)
        initialize_database(self.db)
        with database_connection(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM schema_migrations"
            ).fetchone()[0], 1)

    def test_unique_scheduled_job_prevents_duplicates(self):
        initialize_database(self.db)
        row = ("run1", "scan", "2026-10-08T13:00:00Z",
               "2026-10-08T13:00:01Z", "RUNNING", "0.4.0")
        sql = ("INSERT INTO job_runs(id,job_name,scheduled_for_utc,"
               "started_at_utc,status,config_version) VALUES(?,?,?,?,?,?)")
        with database_connection(self.db) as conn:
            conn.execute(sql, row)
        with self.assertRaises(sqlite3.IntegrityError):
            with database_connection(self.db) as conn:
                conn.execute(sql, ("run2", *row[1:]))

    def test_transaction_rollback(self):
        initialize_database(self.db)
        with self.assertRaises(ValueError):
            with database_connection(self.db) as conn:
                conn.execute(
                    "INSERT INTO job_runs(id,job_name,scheduled_for_utc,"
                    "started_at_utc,status,config_version) "
                    "VALUES ('r','scan','t','t','RUNNING','v')"
                )
                raise ValueError("rollback")
        with database_connection(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM job_runs"
            ).fetchone()[0], 0)

    def test_foreign_keys_enforced(self):
        initialize_database(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            with database_connection(self.db) as conn:
                conn.execute(
                    "INSERT INTO scan_candidates "
                    "(scan_run_id,symbol,quality_pass,observed_at_utc,raw_result_json)"
                    " VALUES ('missing','FRSH',1,'t','{}')"
                )

    def test_future_schema_rejected(self):
        initialize_database(self.db)
        with database_connection(self.db) as conn:
            conn.execute(
                "INSERT INTO schema_migrations(version,applied_at_utc)"
                " VALUES (999,'t')"
            )
        with self.assertRaises(RuntimeError):
            initialize_database(self.db)


if __name__ == "__main__":
    unittest.main()
