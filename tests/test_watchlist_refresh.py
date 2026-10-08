"""Phase 2.3 refresh tests; all database writes use temporary SQLite."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from tradepilot.storage.database import database_connection, initialize_database
from tradepilot.watchlist_refresh import preview_refresh, refresh


class RefreshTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.db"
        initialize_database(self.db)
        with database_connection(self.db) as conn:
            conn.execute(
                """INSERT INTO scan_runs
                (id,universe_name,started_at_utc,finished_at_utc,status,config_snapshot_json)
                VALUES ('seed','Test','2026-10-07T15:00:00Z','2026-10-07T15:00:00Z','SUCCEEDED','{}')"""
            )
            for symbol, state in (("AAPL", "WATCHING"), ("WALMEX.MX", "PROMOTED"),
                                  ("MSFT", "REMOVED"), ("ALSEA.MX", "EXPIRED")):
                conn.execute(
                    """INSERT INTO watchlist_entries
                    (symbol,market,state,first_seen_at_utc,last_seen_at_utc,last_scan_run_id)
                    VALUES (?,?,?,?,?,?)""",
                    (symbol, "MX" if symbol.endswith(".MX") else "US", state,
                     "2026-10-07T15:00:00Z", "2026-10-07T15:00:00Z", "seed"),
                )

    def test_preview_only_active(self):
        plan = preview_refresh(db_path=self.db)
        self.assertEqual(set(plan["symbols"]), {"AAPL", "WALMEX.MX"})
        self.assertEqual(plan["excluded_terminal"], 2)

    def test_limit_fails_closed(self):
        with self.assertRaises(ValueError):
            preview_refresh(db_path=self.db, limit=1)
        with self.assertRaises(ValueError):
            preview_refresh(db_path=self.db, limit=0)

    def test_run_uses_existing_scanner_and_persists_research_only(self):
        outcome = Mock()
        outcome.results = [{"ticker": "AAPL"}]
        outcome.quality_passed = [{"ticker": "AAPL"}]
        scanner = Mock(return_value=outcome)
        saver = Mock(return_value="newscan")
        result = refresh(db_path=self.db, scanner=scanner, saver=saver)
        self.assertEqual(result["scan_id"], "newscan")
        self.assertFalse(result["freshness_verified"])
        scanner.assert_called_once()
        kwargs = scanner.call_args.kwargs
        self.assertEqual(set(kwargs["tickers"]), {"AAPL", "WALMEX.MX"})
        self.assertEqual(kwargs["etf_tickers"], [])
        self.assertEqual(saver.call_args.kwargs["config_snapshot"]["research_only"], True)

    def test_empty_active_skips_without_scanning(self):
        with database_connection(self.db) as conn:
            conn.execute("UPDATE watchlist_entries SET state='REMOVED'")
        scanner = Mock()
        result = refresh(db_path=self.db, scanner=scanner)
        self.assertEqual(result["status"], "SKIPPED")
        scanner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
