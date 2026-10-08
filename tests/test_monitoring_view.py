"""Pure monitoring view helper regression tests."""
import unittest

from tradepilot.monitoring_view import (
    candidate_rows, elapsed_label, filter_history, heartbeat_label,
    local_timestamp, status_label,
)


class MonitoringViewTests(unittest.TestCase):
    def test_local_timestamp_requires_timezone(self):
        self.assertEqual(local_timestamp(None), "—")
        with self.assertRaises(ValueError):
            local_timestamp("2026-10-08T10:00:00")
        self.assertIn("2026-10-08", local_timestamp("2026-10-08T12:00:00Z"))

    def test_duration_labels(self):
        self.assertEqual(elapsed_label(None), "—")
        self.assertEqual(elapsed_label(2.3), "2.3 s")
        self.assertEqual(elapsed_label(65), "1m 5.0s")
        with self.assertRaises(ValueError):
            elapsed_label(-1)

    def test_status_and_heartbeat_labels(self):
        self.assertEqual(status_label("SUCCEEDED"), "Completed")
        self.assertEqual(heartbeat_label("NOT_RUNNING"), "Finished / inactive")
        self.assertEqual(heartbeat_label("STALE_UNVERIFIED"), "Stale — investigate")

    def test_filter_history_does_not_mutate(self):
        rows = [
            {"status": "SUCCEEDED", "universe_name": "A"},
            {"status": "FAILED", "universe_name": "B"},
        ]
        self.assertEqual(len(filter_history(rows)), 2)
        self.assertEqual(filter_history(rows, status="FAILED"), [rows[1]])
        self.assertEqual(filter_history(rows, universe="A"), [rows[0]])
        self.assertEqual(rows[0]["status"], "SUCCEEDED")

    def test_candidate_quality_filter_and_rank(self):
        data = [
            {"ticker": "BBB", "quality_gate": {"passed": False},
             "opportunity": {"score": 95}},
            {"ticker": "AAA", "quality_gate": {"passed": True},
             "opportunity": {"score": 65}},
            {"ticker": "CCC", "quality_gate": {"passed": True},
             "opportunity": {"score": 80}},
        ]
        ranked = candidate_rows(data)
        self.assertEqual([r["Ticker"] for r in ranked], ["CCC", "AAA", "BBB"])
        self.assertEqual([r["Ticker"] for r in candidate_rows(data, quality_only=True)],
                         ["CCC", "AAA"])
        self.assertEqual(data[0]["ticker"], "BBB")


if __name__ == "__main__":
    unittest.main()
