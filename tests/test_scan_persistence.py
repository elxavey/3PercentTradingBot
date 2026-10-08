"""Phase 1.4 persistence tests: isolated SQLite, no Yahoo requests."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tradepilot.core.scanner_service import ScanOutcome
from tradepilot.storage.database import SCHEMA_VERSION, database_connection, initialize_database
from tradepilot.storage.scan_repository import get_scan, list_scans, save_scan


def example_outcome():
    return ScanOutcome(
        results=[
            {"ticker": "BBB", "score": 0.7, "price": 101.5,
             "quality_gate": {"passed": True, "market": "US"},
             "opportunity": {"score": 70},
             "timing": {"metadata_seconds": 0.2, "metadata_cache_hit": True,
                        "history_reused": True}},
            {"ticker": "AAA.MX", "score": 0.9, "price": 40.0,
             "quality_gate": {"passed": True, "market": "MX"},
             "opportunity": {"score": 95},
             "timing": {"metadata_seconds": 0.1, "metadata_cache_hit": False,
                        "history_reused": True}},
            {"ticker": "FAIL", "score": 0.3, "price": 5.0,
             "quality_gate": {"passed": False, "market": "US"},
             "opportunity": {"score": 0},
             "timing": {}},
        ],
        universe_result={
            "total": 4, "passed": [
                {"ticker": "BBB", "history": object()},
                {"ticker": "AAA.MX", "history": object()},
                {"ticker": "FAIL", "history": object()},
            ],
            "excluded": [{"ticker": "NOPE", "reason": "illiquid"}],
            "history_cache_hits": 3, "seconds": 0.3,
        },
        discovery_result={"discovered": 4, "symbols": ["BBB", "AAA.MX", "FAIL", "NOPE"],
                          "mx": 1, "us": 3, "seconds": 0.1},
        scan_seconds=2.5,
    )


class ScanPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "tradepilot.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_schema_v2_telemetry_table(self):
        self.assertEqual(initialize_database(self.db), SCHEMA_VERSION)
        with database_connection(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM schema_migrations"
            ).fetchone()[0], SCHEMA_VERSION)
            self.assertIsNotNone(conn.execute(
                "SELECT name FROM sqlite_master WHERE name='scan_run_telemetry'"
            ).fetchone())

    def test_save_and_recover_all_results(self):
        scan_id = save_scan(example_outcome(), universe_name="Test 12",
                            config_snapshot={"threshold": 0.7}, db_path=self.db)
        stored = get_scan(scan_id, db_path=self.db)
        self.assertEqual(stored.status, "SUCCEEDED")
        self.assertEqual(stored.discovered_count, 4)
        self.assertEqual(stored.pre_screen_count, 3)
        self.assertEqual(stored.quality_pass_count, 2)
        self.assertEqual(stored.config_snapshot, {"threshold": 0.7})
        self.assertEqual(len(stored.results), 3)
        self.assertEqual(stored.results[0]["ticker"], "AAA.MX")
        self.assertEqual(stored.timing["metadata_cache_hits"], 1)
        self.assertEqual(stored.timing["history_reused"], 2)
        self.assertEqual(stored.excluded[0]["ticker"], "NOPE")
        self.assertEqual(stored.discovery["mx"], 1)
        self.assertEqual(stored.pre_screen["passed_symbols"], ["BBB", "AAA.MX", "FAIL"])

    def test_persists_across_new_connections(self):
        scan_id = save_scan(example_outcome(), universe_name="Test 12",
                            config_snapshot={}, db_path=self.db)
        self.assertIsNotNone(get_scan(scan_id, db_path=self.db))

    def test_list_scans_newest_and_limit(self):
        save_scan(example_outcome(), universe_name="First",
                  config_snapshot={}, db_path=self.db, scan_id="first")
        save_scan(example_outcome(), universe_name="Second",
                  config_snapshot={}, db_path=self.db, scan_id="second")
        scans = list_scans(db_path=self.db, limit=1)
        self.assertEqual(len(scans), 1)
        self.assertEqual(scans[0]["id"], "second")
        self.assertNotIn("results", scans[0])

    def test_unknown_scan_returns_none(self):
        self.assertIsNone(get_scan("missing", db_path=self.db))

    def test_duplicate_scan_id_rolls_back(self):
        save_scan(example_outcome(), universe_name="First",
                  config_snapshot={}, db_path=self.db, scan_id="same")
        with self.assertRaises(sqlite3.IntegrityError):
            save_scan(example_outcome(), universe_name="Second",
                      config_snapshot={}, db_path=self.db, scan_id="same")
        self.assertEqual(len(list_scans(db_path=self.db)), 1)

    def test_candidate_failure_rolls_back_entire_run(self):
        outcome = example_outcome()
        outcome.results[1]["ticker"] = "BBB"
        with self.assertRaises(sqlite3.IntegrityError):
            save_scan(outcome, universe_name="Collision",
                      config_snapshot={}, db_path=self.db, scan_id="collision")
        self.assertIsNone(get_scan("collision", db_path=self.db))

    def test_unserializable_result_cannot_write_partial_data(self):
        outcome = example_outcome()
        outcome.results[0]["bad"] = object()
        with self.assertRaises(TypeError):
            save_scan(outcome, universe_name="Bad",
                      config_snapshot={}, db_path=self.db)
        self.assertEqual(list_scans(db_path=self.db), [])

    def test_empty_scan_is_recorded(self):
        outcome = ScanOutcome(
            results=[],
            universe_result={"total": 0, "passed": [], "excluded": [], "seconds": 0},
            discovery_result=None,
            scan_seconds=0.1,
        )
        scan_id = save_scan(outcome, universe_name="Empty",
                            config_snapshot={}, db_path=self.db)
        stored = get_scan(scan_id, db_path=self.db)
        self.assertEqual(stored.results, [])
        self.assertEqual(stored.quality_pass_count, 0)

    def test_invalid_limit_and_name(self):
        with self.assertRaises(ValueError):
            list_scans(db_path=self.db, limit=0)
        with self.assertRaises(ValueError):
            save_scan(example_outcome(), universe_name=" ",
                      config_snapshot={}, db_path=self.db)


if __name__ == "__main__":
    unittest.main()
