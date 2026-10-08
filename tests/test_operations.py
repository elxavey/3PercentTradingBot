"""Phase 1.7 operational reliability tests; no external network calls."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tradepilot.operations import heartbeat, operational_status
from tradepilot.storage.database import database_connection, initialize_database
from tradepilot.worker import claim_job, finish_job, execute_once
from tests.test_worker import fake_scan

UTC = timezone.utc
SLOT = "2026-10-08T14:00:00Z"


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "state.sqlite"

    def tearDown(self):
        self.temp.cleanup()

    def test_migration_v3_and_idempotency(self):
        self.assertEqual(initialize_database(self.db), 3)
        self.assertEqual(initialize_database(self.db), 3)
        with database_connection(self.db) as conn:
            self.assertIn("heartbeat_at_utc", [r[1] for r in conn.execute("PRAGMA table_info(job_runs)")])
            self.assertEqual([r[0] for r in conn.execute("SELECT version FROM schema_migrations")], [1, 2, 3])

    def test_running_heartbeat_recent(self):
        job = claim_job(db_path=self.db, scheduled_for_utc=SLOT)
        self.assertTrue(heartbeat(job, db_path=self.db))
        rows = operational_status(db_path=self.db)
        self.assertEqual(rows[0]["heartbeat_state"], "RECENT")

    def test_heartbeat_stale_does_not_unlock(self):
        job = claim_job(db_path=self.db, scheduled_for_utc=SLOT)
        with database_connection(self.db) as conn:
            conn.execute("UPDATE job_runs SET heartbeat_at_utc=? WHERE id=?",
                         ("2020-01-01T00:00:00.000Z", job))
        rows = operational_status(db_path=self.db)
        self.assertEqual(rows[0]["heartbeat_state"], "STALE_UNVERIFIED")
        self.assertIsNone(claim_job(db_path=self.db, scheduled_for_utc="2026-10-08T15:00:00Z"))

    def test_terminal_job_cannot_be_revived(self):
        job = claim_job(db_path=self.db, scheduled_for_utc=SLOT)
        finish_job(job, db_path=self.db, status="SUCCEEDED")
        self.assertFalse(heartbeat(job, db_path=self.db))
        self.assertEqual(operational_status(db_path=self.db)[0]["heartbeat_state"], "NOT_RUNNING")

    def test_unknown_job_returns_false(self):
        initialize_database(self.db)
        self.assertFalse(heartbeat("nonexistent", db_path=self.db))

    def test_reject_invalid_status_arguments(self):
        with self.assertRaises(ValueError):
            operational_status(db_path=self.db, stale_after_seconds=0)
        with self.assertRaises(ValueError):
            operational_status(db_path=self.db, limit=0)
        with self.assertRaises(ValueError):
            operational_status(db_path=self.db, at=datetime(2026, 10, 8))

    def test_successful_worker_has_heartbeat(self):
        code, job = execute_once(db_path=self.db, scheduled_for_utc=SLOT, scanner=fake_scan)
        self.assertEqual(code, 0)
        with database_connection(self.db) as conn:
            value = conn.execute("SELECT heartbeat_at_utc FROM job_runs WHERE id=?", (job,)).fetchone()[0]
        self.assertIsNotNone(value)


if __name__ == "__main__":
    unittest.main()
