"""Read-only 62-symbol expansion report tests."""
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from tradepilot.storage.database import initialize_database
from tradepilot.expansion_validation import expansion_report

NAME = "Broad MX + USA - 62 symbols"


class ExpansionValidationTests(unittest.TestCase):
    def test_missing_database_does_not_create(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "missing.db"
            self.assertEqual(expansion_report(path)["state"], "NO_DATABASE")
            self.assertFalse(path.exists())

    def test_no_scan(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.db"
            initialize_database(path)
            self.assertEqual(expansion_report(path)["state"], "NO_SCAN")

    def test_completed_consistent_scan(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as conn:
                conn.execute(
                    """INSERT INTO scan_runs
                    (id,universe_name,started_at_utc,finished_at_utc,status,
                     discovered_count,pre_screen_count,quality_pass_count,
                     elapsed_seconds,config_snapshot_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    ("run1", NAME, "2026-10-08T10:00:00Z", "2026-10-08T10:05:00Z",
                     "SUCCEEDED", 62, 60, 1, 300, "{}"))
                conn.execute(
                    """INSERT INTO scan_candidates
                    (scan_run_id,symbol,quality_pass,observed_at_utc,raw_result_json)
                    VALUES (?,?,?,?,?)""",
                    ("run1", "ALSEA.MX", 1, "2026-10-08T10:05:00Z", "{}"))
                conn.commit()
            report = expansion_report(path)
            self.assertEqual(report["state"], "READY_FOR_REVIEW")
            self.assertEqual(report["mx_candidates"], 1)
            self.assertEqual(report["persisted_quality_pass"], 1)

    def test_failed_scan_not_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as conn:
                conn.execute(
                    """INSERT INTO scan_runs
                    (id,universe_name,started_at_utc,finished_at_utc,status,
                     discovered_count,pre_screen_count,quality_pass_count,
                     elapsed_seconds,config_snapshot_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    ("run1", NAME, "2026-10-08T10:00:00Z", "2026-10-08T10:05:00Z",
                     "FAILED", 62, 60, 1, 300, "{}"))
                conn.commit()
            self.assertEqual(expansion_report(path)["state"], "NEEDS_REVIEW")


if __name__ == "__main__":
    unittest.main()
