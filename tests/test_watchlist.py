"""Phase 2.1 research watchlist tests with isolated SQLite."""
import tempfile
import unittest
from pathlib import Path

from tradepilot.storage.database import database_connection, initialize_database
from tradepilot.watchlist import list_watchlist, preview_watchlist, update_watchlist


class WatchlistTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "test.db"
        initialize_database(self.db)
        self.add_scan("s1", "2026-10-07T15:00:00Z", [
            ("AAPL", "US", 90, 1), ("WALMEX.MX", "MX", 85, 1),
            ("FAIL", "US", 99, 0), ("LOW", "US", 10, 1),
        ])

    def add_scan(self, sid, stamp, candidates, status="SUCCEEDED"):
        with database_connection(self.db) as conn:
            conn.execute(
                """INSERT INTO scan_runs
                   (id,universe_name,started_at_utc,finished_at_utc,status,
                    config_snapshot_json) VALUES (?,?,?,?,?,?)""",
                (sid, "Test", stamp, stamp, status, "{}"),
            )
            for symbol, market, score, passed in candidates:
                conn.execute(
                    """INSERT INTO scan_candidates
                       (scan_run_id,symbol,exchange_code,currency,quality_pass,
                        opportunity_score,observed_at_utc,raw_result_json)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (sid, symbol, market, "MXN" if market == "MX" else "USD",
                     passed, score, stamp, "{}"),
                )

    def test_preview_does_not_write(self):
        result = preview_watchlist("s1", db_path=self.db, limit=2)
        self.assertEqual([x["symbol"] for x in result["items"]], ["AAPL", "WALMEX.MX"])
        self.assertEqual(list_watchlist(db_path=self.db), [])

    def test_apply_persists_and_is_idempotent(self):
        update_watchlist("s1", db_path=self.db, limit=2)
        update_watchlist("s1", db_path=self.db, limit=2)
        rows = list_watchlist(db_path=self.db)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["symbol"], "AAPL")
        self.assertEqual(rows[1]["market"], "MX")

    def test_reject_invalid_scan_and_limit(self):
        with self.assertRaises(ValueError):
            preview_watchlist("unknown", db_path=self.db)
        with self.assertRaises(ValueError):
            preview_watchlist("s1", db_path=self.db, limit=0)
        with self.assertRaises(ValueError):
            preview_watchlist("s1", db_path=self.db, limit=51)
        self.add_scan("failed", "2026-10-08T15:00:00Z", [], status="FAILED")
        with self.assertRaises(ValueError):
            update_watchlist("failed", db_path=self.db)

    def test_new_scan_refreshes_and_retains_other_entries(self):
        update_watchlist("s1", db_path=self.db, limit=2)
        self.add_scan("s2", "2026-10-08T15:00:00Z", [
            ("AAPL", "US", 70, 1), ("MSFT", "US", 98, 1),
        ])
        update_watchlist("s2", db_path=self.db, limit=2)
        rows = list_watchlist(db_path=self.db)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["symbol"], "MSFT")
        self.assertEqual({r["symbol"] for r in rows}, {"AAPL", "MSFT", "WALMEX.MX"})

    def test_historical_scan_rejected_without_partial_writes(self):
        self.add_scan("s2", "2026-10-08T15:00:00Z", [("MSFT", "US", 98, 1)])
        update_watchlist("s2", db_path=self.db)
        with self.assertRaises(ValueError):
            update_watchlist("s1", db_path=self.db)
        self.assertEqual([r["symbol"] for r in list_watchlist(db_path=self.db)], ["MSFT"])


if __name__ == "__main__":
    unittest.main()
