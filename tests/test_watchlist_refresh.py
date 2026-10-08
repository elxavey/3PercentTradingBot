"""Phase 2.3 refresh tests; all database writes use temporary SQLite."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from tradepilot.storage.database import database_connection, initialize_database
from tradepilot.watchlist_refresh import compare_refresh, preview_refresh, refresh


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


    def test_comparison_score_delta_and_unknown_freshness(self):
        with database_connection(self.db) as conn:
            conn.execute(
                """INSERT INTO scan_candidates
                   (scan_run_id,symbol,exchange_code,currency,quality_pass,
                    opportunity_score,observed_at_utc,raw_result_json)
                   VALUES ('seed','AAPL','US','USD',1,60,
                           '2026-10-07T15:00:00Z','{}')"""
            )
            conn.execute(
                """INSERT INTO scan_runs
                   (id,universe_name,started_at_utc,finished_at_utc,status,
                    config_snapshot_json)
                   VALUES ('new','Watchlist incremental research',
                           '2026-10-08T15:00:00Z','2026-10-08T15:00:00Z',
                           'SUCCEEDED','{}')"""
            )
            conn.execute(
                """INSERT INTO scan_candidates
                   (scan_run_id,symbol,exchange_code,currency,quality_pass,
                    opportunity_score,observed_at_utc,raw_result_json)
                   VALUES ('new','AAPL','US','USD',1,75,
                           '2026-10-08T15:00:00Z','{}')"""
            )
        result = compare_refresh("new", db_path=self.db)
        items = {r["symbol"]: r for r in result["items"]}
        self.assertEqual(items["AAPL"]["previous_score"], 60)
        self.assertEqual(items["AAPL"]["new_score"], 75)
        self.assertEqual(items["AAPL"]["delta"], 15)
        self.assertEqual(items["WALMEX.MX"]["quality_gate"], "NOT_EVALUATED")
        self.assertIsNone(items["WALMEX.MX"]["delta"])
        self.assertEqual(items["AAPL"]["market_data_freshness"], "UNKNOWN")
        self.assertFalse(result["freshness_verified"])

    def test_comparison_rejects_unrelated_scan(self):
        with self.assertRaises(ValueError):
            compare_refresh("seed", db_path=self.db)
        with self.assertRaises(ValueError):
            compare_refresh("missing", db_path=self.db)

    def test_empty_active_skips_without_scanning(self):
        with database_connection(self.db) as conn:
            conn.execute("UPDATE watchlist_entries SET state='REMOVED'")
        scanner = Mock()
        result = refresh(db_path=self.db, scanner=scanner)
        self.assertEqual(result["status"], "SKIPPED")
        scanner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
