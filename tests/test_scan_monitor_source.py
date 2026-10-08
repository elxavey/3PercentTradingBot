"""Read-only saved scan monitor source acceptance tests."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from tradepilot.scan_monitor_source import scan_monitor_entries
from tradepilot.storage.database import initialize_database


class ScanMonitorSourceTests(unittest.TestCase):
    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "absent.db"
            with self.assertRaises(ValueError):
                scan_monitor_entries("scan", db_path=path)
            self.assertFalse(path.exists())

    def test_invalid_limit(self):
        with self.assertRaises(ValueError):
            scan_monitor_entries("scan", limit=51)

    def test_unknown_scan_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "test.db"
            initialize_database(path)
            with self.assertRaises(ValueError):
                scan_monitor_entries("missing", db_path=path)

    def test_saved_scan_sorted_and_no_watchlist_writes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "test.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as conn:
                conn.execute(
                    """INSERT INTO scan_runs
                    (id,universe_name,started_at_utc,finished_at_utc,status,
                     config_snapshot_json)
                    VALUES (?,?,?,?,?,?)""",
                    ("scan", "Broad MX + USA - 62 symbols",
                     "2026-10-08T18:00:00Z", "2026-10-08T18:01:00Z",
                     "SUCCEEDED", "{}"))
                for symbol, score, quality in [
                    ("ALSEA.MX", 50.0, 1), ("META", 80.0, 1),
                    ("AAPL", 70.0, 1), ("BAD", 100.0, 0)]:
                    conn.execute(
                        """INSERT INTO scan_candidates
                        (scan_run_id,symbol,quality_pass,opportunity_score,
                         observed_at_utc,raw_result_json)
                        VALUES (?,?,?,?,?,?)""",
                        ("scan", symbol, quality, score,
                         "2026-10-08T18:01:00Z", "{}"))
                conn.commit()
            result = scan_monitor_entries("scan", db_path=path, limit=2)
            self.assertEqual([x["symbol"] for x in result["entries"]],
                             ["META", "AAPL"])
            self.assertEqual(result["entries"][0]["state"], "SCAN_PREVIEW")
            with closing(sqlite3.connect(path)) as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM watchlist_entries").fetchone()[0], 0)
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM watchlist_events").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
