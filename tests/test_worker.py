"""Phase 1.5: worker lifecycle and concurrency, no live network calls."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tradepilot.core.scanner_service import ScanOutcome
from tradepilot.storage.database import database_connection, initialize_database
from tradepilot.storage.scan_repository import get_scan
from tradepilot.worker import (
    JOB_NAME, claim_job, execute_once, finish_job, interrupt_stale_job, main,
)

SLOT = "2026-10-08T14:00:00Z"


def fake_scan(**kwargs):
    return ScanOutcome(
        results=[{"ticker": "AAPL", "price": 100.0, "score": 0.8,
                  "quality_gate": {"passed": True, "market": "US"},
                  "opportunity": {"score": 80}, "timing": {}}],
        universe_result={"total": 1, "passed": [{"ticker": "AAPL", "history": object()}],
                         "excluded": [], "seconds": 0.01, "history_cache_hits": 1},
        discovery_result=None, scan_seconds=0.1,
    )


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "db.sqlite"

    def tearDown(self):
        self.temp.cleanup()

    def jobs(self):
        with database_connection(self.db) as conn:
            return conn.execute("SELECT id,status,error_message FROM job_runs").fetchall()

    def test_success_persists_scan_linked_to_job(self):
        code, job_id = execute_once(db_path=self.db, scheduled_for_utc=SLOT, scanner=fake_scan)
        self.assertEqual(code, 0)
        self.assertEqual(self.jobs()[0][1], "SUCCEEDED")
        with database_connection(self.db) as conn:
            scan_id = conn.execute("SELECT id FROM scan_runs WHERE job_run_id=?", (job_id,)).fetchone()[0]
        self.assertEqual(get_scan(scan_id, db_path=self.db).results[0]["ticker"], "AAPL")

    def test_duplicate_slot_skipped_after_success(self):
        execute_once(db_path=self.db, scheduled_for_utc=SLOT, scanner=fake_scan)
        code, job = execute_once(db_path=self.db, scheduled_for_utc=SLOT, scanner=fake_scan)
        self.assertEqual((code, job), (2, None))
        self.assertEqual(len(self.jobs()), 1)

    def test_active_job_blocks_different_slot(self):
        job = claim_job(db_path=self.db, scheduled_for_utc=SLOT)
        self.assertIsNotNone(job)
        self.assertIsNone(claim_job(db_path=self.db, scheduled_for_utc="2026-10-08T15:00:00Z"))
        self.assertEqual(len(self.jobs()), 1)

    def test_failed_scan_records_failure_and_no_scan(self):
        def broken(**kwargs):
            raise RuntimeError("Provider failed")
        code, job = execute_once(db_path=self.db, scheduled_for_utc=SLOT, scanner=broken)
        self.assertEqual(code, 1)
        self.assertEqual(self.jobs()[0][1], "FAILED")
        self.assertIn("RuntimeError", self.jobs()[0][2])
        with database_connection(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0], 0)

    def test_persistence_failure_records_failure(self):
        def broken_persist(*args, **kwargs):
            raise sqlite3.OperationalError("db unavailable")
        code, _ = execute_once(db_path=self.db, scheduled_for_utc=SLOT,
                               scanner=fake_scan, persist=broken_persist)
        self.assertEqual(code, 1)
        self.assertEqual(self.jobs()[0][1], "FAILED")

    def test_explicit_interruption_releases_block_but_not_slot(self):
        first = claim_job(db_path=self.db, scheduled_for_utc=SLOT)
        self.assertTrue(interrupt_stale_job(db_path=self.db, job_id=first))
        self.assertFalse(interrupt_stale_job(db_path=self.db, job_id=first))
        self.assertIsNone(claim_job(db_path=self.db, scheduled_for_utc=SLOT))
        self.assertIsNotNone(claim_job(
            db_path=self.db, scheduled_for_utc="2026-10-08T15:00:00Z"
        ))

    def test_cannot_finish_job_twice(self):
        job = claim_job(db_path=self.db, scheduled_for_utc=SLOT)
        finish_job(job, db_path=self.db, status="SUCCEEDED")
        with self.assertRaises(RuntimeError):
            finish_job(job, db_path=self.db, status="FAILED")

    def test_reject_unknown_universe_before_claim(self):
        with self.assertRaises(ValueError):
            execute_once(universe_name="not configured", db_path=self.db, scanner=fake_scan)
        self.assertFalse(self.db.exists())

    def test_reject_naive_slot_before_claim(self):
        with self.assertRaises(ValueError):
            execute_once(db_path=self.db, scheduled_for_utc="2026-10-08T14:00:00",
                         scanner=fake_scan)
        self.assertFalse(self.db.exists())

    def test_normalize_equivalent_timezone_slots(self):
        a = claim_job(db_path=self.db, scheduled_for_utc=SLOT)
        finish_job(a, db_path=self.db, status="SUCCEEDED")
        code, _ = execute_once(db_path=self.db,
                               scheduled_for_utc="2026-10-08T10:00:00-04:00",
                               scanner=fake_scan)
        self.assertEqual(code, 2)

    def test_cli_has_no_streamlit_dependency(self):
        import inspect
        import tradepilot.worker as worker
        self.assertNotIn("import streamlit", inspect.getsource(worker))

    def test_cli_help(self):
        with self.assertRaises(SystemExit) as raised:
            main(["--help"])
        self.assertEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
