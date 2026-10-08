"""Monitoring snapshot tests: no mutations, including stale job state."""
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tradepilot.monitoring import monitoring_snapshot
from tradepilot.storage.database import initialize_database, database_connection

UTC = timezone.utc


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "monitoring.db"
        initialize_database(self.db)

    def test_empty_database(self):
        result = monitoring_snapshot(db_path=self.db)
        self.assertIsNone(result["latest_job"])
        self.assertIsNone(result["latest_scan"])
        self.assertEqual(result["jobs"], [])
        self.assertEqual(result["scans"], [])
        self.assertEqual(result["warnings"], [])

    def test_invalid_limit_and_age(self):
        with self.assertRaises(ValueError):
            monitoring_snapshot(db_path=self.db, limit=0)
        with self.assertRaises(ValueError):
            monitoring_snapshot(db_path=self.db, limit=101)
        with self.assertRaises(ValueError):
            monitoring_snapshot(db_path=self.db, stale_after_seconds=0)

    def test_running_job_is_not_modified(self):
        now = datetime(2026, 10, 8, 18, tzinfo=UTC)
        old = (now - timedelta(minutes=10)).isoformat()
        with database_connection(self.db) as conn:
            conn.execute(
                """INSERT INTO job_runs
                   (id,job_name,scheduled_for_utc,started_at_utc,status,config_version)
                   VALUES (?,?,?,?,?,?)""",
                ("j1", "market_scan", old, old, "RUNNING", "test"),
            )
        result = monitoring_snapshot(db_path=self.db, at=now)
        self.assertEqual(result["jobs"][0]["heartbeat_state"], "STALE_UNVERIFIED")
        self.assertEqual(len(result["warnings"]), 1)
        with database_connection(self.db) as conn:
            state = conn.execute("SELECT status FROM job_runs WHERE id='j1'").fetchone()[0]
        self.assertEqual(state, "RUNNING")

    def test_joined_scan_summary_and_history_order(self):
        with database_connection(self.db) as conn:
            for i in range(2):
                conn.execute(
                    """INSERT INTO job_runs
                       (id,job_name,scheduled_for_utc,started_at_utc,
                        finished_at_utc,status,config_version)
                       VALUES (?,?,?,?,?,?,?)""",
                    (f"j{i}", "market_scan", f"2026-10-0{i+1}T14:45:00Z",
                     f"2026-10-0{i+1}T14:45:00Z",
                     f"2026-10-0{i+1}T14:46:00Z", "SUCCEEDED", "test"),
                )
            conn.execute(
                """INSERT INTO scan_runs
                   (id,job_run_id,universe_name,started_at_utc,finished_at_utc,
                    status,discovered_count,pre_screen_count,quality_pass_count,
                    elapsed_seconds,config_snapshot_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                ("s1", "j1", "Test - 12 symbols", "2026-10-02T14:45:00Z",
                 "2026-10-02T14:46:00Z", "SUCCEEDED", 12, 9, 4, 60.0, "{}"),
            )
        result = monitoring_snapshot(db_path=self.db, limit=2)
        self.assertEqual([r["job_id"] for r in result["jobs"]], ["j1", "j0"])
        self.assertEqual(result["jobs"][0]["scan_id"], "s1")
        self.assertEqual(result["jobs"][0]["quality_pass_count"], 4)
        self.assertIsNone(result["jobs"][1]["scan_id"])
        self.assertEqual(result["latest_scan"]["id"], "s1")

    def test_limit_and_no_sensitive_config_in_snapshot(self):
        with database_connection(self.db) as conn:
            for i in range(3):
                conn.execute(
                    """INSERT INTO job_runs
                       (id,job_name,scheduled_for_utc,started_at_utc,status,config_version)
                       VALUES (?,?,?,?,?,?)""",
                    (f"j{i}", "market_scan", f"2026-10-0{i+1}T14:45:00Z",
                     f"2026-10-0{i+1}T14:45:00Z", "FAILED", "test"),
                )
        result = monitoring_snapshot(db_path=self.db, limit=1)
        self.assertEqual(len(result["jobs"]), 1)
        self.assertNotIn("config_snapshot_json", str(result))


if __name__ == "__main__":
    unittest.main()
