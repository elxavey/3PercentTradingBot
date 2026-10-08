"""Phase 2.2: lifecycle transitions, audit and migration regression tests."""
import tempfile
import unittest
from pathlib import Path

from tradepilot.storage.database import database_connection, initialize_database
from tradepilot.watchlist import (
    apply_session_expiry, list_watchlist, preview_session_expiry,
    set_watchlist_state, update_watchlist, watchlist_history,
)


class WatchlistLifecycleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "test.db"
        self.assertEqual(initialize_database(self.db), 4)
        self.add_scan("s1", "2026-10-07T15:00:00Z", [("AAPL", 80), ("MSFT", 60)])

    def add_scan(self, sid, stamp, symbols):
        with database_connection(self.db) as conn:
            conn.execute(
                """INSERT INTO scan_runs
                   (id,universe_name,started_at_utc,finished_at_utc,status,
                    config_snapshot_json) VALUES (?,?,?,?,?,?)""",
                (sid, "Test", stamp, stamp, "SUCCEEDED", "{}"),
            )
            for symbol, score in symbols:
                conn.execute(
                    """INSERT INTO scan_candidates
                       (scan_run_id,symbol,exchange_code,currency,quality_pass,
                        opportunity_score,observed_at_utc,raw_result_json)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (sid, symbol, "US", "USD", 1, score, stamp, "{}"),
                )

    def test_promotion_threshold_and_initial_events(self):
        update_watchlist("s1", db_path=self.db)
        states = {r["symbol"]: r["state"] for r in list_watchlist(db_path=self.db)}
        self.assertEqual(states, {"AAPL": "PROMOTED", "MSFT": "WATCHING"})
        history = watchlist_history("AAPL", "US", db_path=self.db)
        self.assertEqual(len(history), 1)
        self.assertIsNone(history[0]["previous_state"])
        self.assertEqual(history[0]["new_score"], 80)

    def test_same_scan_replay_does_not_duplicate_audit(self):
        update_watchlist("s1", db_path=self.db)
        update_watchlist("s1", db_path=self.db)
        self.assertEqual(len(watchlist_history("AAPL", "US", db_path=self.db)), 1)

    def test_score_changes_and_demotion_are_audited(self):
        update_watchlist("s1", db_path=self.db)
        self.add_scan("s2", "2026-10-08T15:00:00Z", [("AAPL", 55), ("MSFT", 75)])
        update_watchlist("s2", db_path=self.db)
        aapl = watchlist_history("AAPL", "US", db_path=self.db)
        self.assertEqual(aapl[0]["previous_state"], "PROMOTED")
        self.assertEqual(aapl[0]["new_state"], "WATCHING")
        self.assertEqual((aapl[0]["previous_score"], aapl[0]["new_score"]), (80, 55))
        self.assertEqual(watchlist_history("MSFT", "US", db_path=self.db)[0]["new_state"], "PROMOTED")

    def test_manual_expiry_and_no_silent_reactivation(self):
        update_watchlist("s1", db_path=self.db)
        self.assertTrue(set_watchlist_state("AAPL", "US", "EXPIRED", db_path=self.db))
        self.assertFalse(set_watchlist_state("AAPL", "US", "EXPIRED", db_path=self.db))
        self.add_scan("s2", "2026-10-08T15:00:00Z", [("AAPL", 99)])
        update_watchlist("s2", db_path=self.db)
        aapl = next(r for r in list_watchlist(db_path=self.db) if r["symbol"] == "AAPL")
        self.assertEqual(aapl["state"], "EXPIRED")
        self.assertEqual(len(watchlist_history("AAPL", "US", db_path=self.db)), 2)

    def test_removed_is_terminal(self):
        update_watchlist("s1", db_path=self.db)
        self.assertTrue(set_watchlist_state("MSFT", "US", "REMOVED", db_path=self.db))
        with self.assertRaises(ValueError):
            set_watchlist_state("MSFT", "US", "EXPIRED", db_path=self.db)

    def test_invalid_manual_transition_no_mutation(self):
        update_watchlist("s1", db_path=self.db)
        with self.assertRaises(ValueError):
            set_watchlist_state("AAPL", "US", "PROMOTED", db_path=self.db)
        with self.assertRaises(ValueError):
            set_watchlist_state("FAKE", "US", "REMOVED", db_path=self.db)
        self.assertEqual(len(watchlist_history("AAPL", "US", db_path=self.db)), 1)


    def add_failed_scan(self, sid, stamp, symbol="AAPL", universe="Test"):
        with database_connection(self.db) as conn:
            conn.execute(
                """INSERT INTO scan_runs
                   (id,universe_name,started_at_utc,finished_at_utc,status,
                    config_snapshot_json) VALUES (?,?,?,?,?,?)""",
                (sid, universe, stamp, stamp, "SUCCEEDED", "{}"),
            )
            conn.execute(
                """INSERT INTO scan_candidates
                   (scan_run_id,symbol,exchange_code,currency,quality_pass,
                    opportunity_score,observed_at_utc,raw_result_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (sid, symbol, "US", "USD", 0, 20, stamp, "{}"),
            )

    def test_three_consecutive_failed_sessions_preview_and_apply(self):
        update_watchlist("s1", db_path=self.db)
        self.add_failed_scan("f1", "2026-10-08T15:00:00Z")
        self.add_failed_scan("f2", "2026-10-09T15:00:00Z")
        self.add_failed_scan("f3", "2026-10-12T15:00:00Z")
        preview = preview_session_expiry("f3", db_path=self.db)
        self.assertEqual([i["symbol"] for i in preview["items"]], ["AAPL"])
        self.assertEqual(
            next(r["state"] for r in list_watchlist(db_path=self.db)
                 if r["symbol"] == "AAPL"), "PROMOTED",
        )
        self.assertEqual(apply_session_expiry("f3", db_path=self.db)["expired"], 1)
        self.assertEqual(apply_session_expiry("f3", db_path=self.db)["expired"], 0)
        self.assertEqual(
            watchlist_history("AAPL", "US", db_path=self.db)[0]["reason"],
            "AUTO_QUALITY_FAIL_3_SESSIONS",
        )

    def test_missing_session_breaks_failure_streak(self):
        update_watchlist("s1", db_path=self.db)
        self.add_failed_scan("f1", "2026-10-08T15:00:00Z")
        self.add_failed_scan("f2", "2026-10-12T15:00:00Z")
        self.add_failed_scan("f3", "2026-10-13T15:00:00Z")
        self.assertEqual(preview_session_expiry("f3", db_path=self.db)["items"], [])

    def test_missing_symbol_does_not_count_as_failure(self):
        update_watchlist("s1", db_path=self.db)
        self.add_failed_scan("f1", "2026-10-08T15:00:00Z")
        self.add_failed_scan("f2", "2026-10-09T15:00:00Z", symbol="GOOG")
        self.add_failed_scan("f3", "2026-10-12T15:00:00Z")
        self.assertEqual(preview_session_expiry("f3", db_path=self.db)["items"], [])

    def test_different_universe_does_not_count(self):
        update_watchlist("s1", db_path=self.db)
        self.add_failed_scan("f1", "2026-10-08T15:00:00Z", universe="Other")
        self.add_failed_scan("f2", "2026-10-09T15:00:00Z")
        self.add_failed_scan("f3", "2026-10-12T15:00:00Z")
        self.assertEqual(preview_session_expiry("f3", db_path=self.db)["items"], [])

    def test_latest_quality_pass_prevents_expiry(self):
        update_watchlist("s1", db_path=self.db)
        self.add_failed_scan("f1", "2026-10-08T15:00:00Z")
        self.add_failed_scan("f2", "2026-10-09T15:00:00Z")
        self.add_scan("pass", "2026-10-12T15:00:00Z", [("AAPL", 80)])
        self.assertEqual(preview_session_expiry("pass", db_path=self.db)["items"], [])

    def test_expiry_preview_rejects_invalid_inputs(self):
        with self.assertRaises(ValueError):
            preview_session_expiry("unknown", db_path=self.db)
        with self.assertRaises(ValueError):
            preview_session_expiry("s1", db_path=self.db, failed_sessions=1)

    def test_schema_migration_is_idempotent(self):
        self.assertEqual(initialize_database(self.db), 4)
        with database_connection(self.db) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE version=4"
            ).fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
