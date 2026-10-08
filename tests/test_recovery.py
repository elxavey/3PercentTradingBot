"""Safe recovery tests: isolated SQLite; no network calls."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tradepilot.recovery import recover_interrupted_job
from tradepilot.storage.database import database_connection
from tradepilot.worker import claim_job, finish_job

UTC = timezone.utc
NOW = datetime(2026, 10, 8, 15, 0, tzinfo=UTC)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "test.db"
        self.job = claim_job(db_path=self.db, scheduled_for_utc="2026-10-08T14:00:00Z")
        with database_connection(self.db) as conn:
            conn.execute("UPDATE job_runs SET started_at_utc=?, heartbeat_at_utc=? WHERE id=?",
                         ("2026-10-08T14:00:00.000Z", "2026-10-08T14:00:00.000Z", self.job))

    def tearDown(self):
        self.temp.cleanup()

    def status(self):
        with database_connection(self.db) as conn:
            return conn.execute("SELECT status FROM job_runs WHERE id=?", (self.job,)).fetchone()[0]

    def test_confirmation_required(self):
        with self.assertRaises(ValueError):
            recover_interrupted_job(self.job, db_path=self.db, at=NOW)
        self.assertEqual(self.status(), "RUNNING")

    def test_old_heartbeat_and_confirmation_allows_recovery(self):
        self.assertTrue(recover_interrupted_job(self.job, db_path=self.db,
                                                at=NOW, confirmed_stopped=True))
        self.assertEqual(self.status(), "INTERRUPTED")

    def test_recent_heartbeat_blocks_recovery(self):
        with database_connection(self.db) as conn:
            conn.execute("UPDATE job_runs SET heartbeat_at_utc=? WHERE id=?",
                         ("2026-10-08T14:59:00.000Z", self.job))
        self.assertFalse(recover_interrupted_job(self.job, db_path=self.db,
                                                 at=NOW, confirmed_stopped=True))
        self.assertEqual(self.status(), "RUNNING")

    def test_terminal_job_cannot_recover(self):
        finish_job(self.job, db_path=self.db, status="SUCCEEDED")
        self.assertFalse(recover_interrupted_job(self.job, db_path=self.db,
                                                 at=NOW, confirmed_stopped=True))

    def test_recovered_slot_remains_reserved(self):
        self.assertTrue(recover_interrupted_job(self.job, db_path=self.db,
                                                at=NOW, confirmed_stopped=True))
        self.assertIsNone(claim_job(db_path=self.db, scheduled_for_utc="2026-10-08T14:00:00Z"))
        self.assertIsNotNone(claim_job(db_path=self.db, scheduled_for_utc="2026-10-08T15:00:00Z"))

    def test_invalid_arguments_fail_closed(self):
        with self.assertRaises(ValueError):
            recover_interrupted_job(self.job, db_path=self.db, at=NOW,
                                    confirmed_stopped=True, min_age_seconds=0)
        with self.assertRaises(ValueError):
            recover_interrupted_job(self.job, db_path=self.db,
                                    at=datetime(2026, 10, 8, 15), confirmed_stopped=True)

    def test_no_heartbeat_uses_started_timestamp(self):
        with database_connection(self.db) as conn:
            conn.execute("UPDATE job_runs SET heartbeat_at_utc=NULL WHERE id=?", (self.job,))
        self.assertTrue(recover_interrupted_job(self.job, db_path=self.db,
                                                at=NOW, confirmed_stopped=True))


if __name__ == "__main__":
    unittest.main()
