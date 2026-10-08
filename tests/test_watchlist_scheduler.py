"""Phase 2.4 schedule, SQLite deduplication and failure tests."""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from tradepilot.storage.database import database_connection
from tradepilot.watchlist_scheduler import due_watchlist_slot, tick

UTC = timezone.utc
DUE = datetime(2026, 10, 8, 15, 45, tzinfo=UTC)


class WatchlistSchedulerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.db"

    def test_due_after_both_markets_open(self):
        self.assertIsNotNone(due_watchlist_slot(DUE))
        self.assertIsNone(due_watchlist_slot(datetime(2026, 10, 8, 14, 45, tzinfo=UTC)))

    def test_weekend_not_due(self):
        runner = Mock()
        self.assertEqual(tick(now=datetime(2026, 10, 10, 15, 45, tzinfo=UTC),
                              db_path=self.db, runner=runner)["status"], "NOT_DUE")
        runner.assert_not_called()

    def test_dry_run_does_not_persist_or_scan(self):
        runner = Mock()
        self.assertEqual(tick(now=DUE, db_path=self.db, dry_run=True,
                              runner=runner)["status"], "DRY_RUN")
        self.assertFalse(self.db.exists())
        runner.assert_not_called()

    def test_success_and_duplicate_slot(self):
        runner = Mock(return_value={"status": "SUCCEEDED", "scan_id": "abc",
                                    "evaluated": 12})
        first = tick(now=DUE, db_path=self.db, runner=runner)
        second = tick(now=DUE, db_path=self.db, runner=runner)
        self.assertEqual(first["status"], "SUCCEEDED")
        self.assertEqual(second["reason"], "SLOT_ALREADY_CLAIMED")
        runner.assert_called_once()
        with database_connection(self.db) as conn:
            row = conn.execute(
                "SELECT job_name,status FROM job_runs WHERE id=?",
                (first["job_id"],),
            ).fetchone()
        self.assertEqual(row, ("watchlist_refresh", "SUCCEEDED"))

    def test_failed_job_recorded_without_replay(self):
        runner = Mock(side_effect=RuntimeError("secret provider error"))
        result = tick(now=DUE, db_path=self.db, runner=runner)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(tick(now=DUE, db_path=self.db, runner=runner)["status"],
                         "SKIPPED")
        runner.assert_called_once()
        with database_connection(self.db) as conn:
            error = conn.execute(
                "SELECT error_message FROM job_runs WHERE id=?", (result["job_id"],)
            ).fetchone()[0]
        self.assertNotIn("secret provider error", error)

    def test_empty_watchlist_is_skipped(self):
        runner = Mock(return_value={"status": "SKIPPED", "reason": "EMPTY_WATCHLIST"})
        result = tick(now=DUE, db_path=self.db, runner=runner)
        self.assertEqual(result["status"], "SKIPPED")

    def test_invalid_limit_and_naive_clock(self):
        with self.assertRaises(ValueError):
            tick(now=DUE, db_path=self.db, limit=0)
        with self.assertRaises(ValueError):
            due_watchlist_slot(datetime(2026, 10, 8, 15, 45))


if __name__ == "__main__":
    unittest.main()
