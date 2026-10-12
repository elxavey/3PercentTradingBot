import unittest
from tradepilot.v6_stop_target_cli import analyze


class StopTargetTests(unittest.TestCase):
    def setUp(self):
        self.cases = [
            {"case_id": "1", "symbol": "AAA", "market": "US", "strategy": "BREAKOUT",
             "signal_date": "2023-01-01", "fixed_outcome": "STOP", "fixed_net_pct": "-3.5"},
            {"case_id": "2", "symbol": "BBB", "market": "US", "strategy": "REBOUND",
             "signal_date": "2023-01-02", "fixed_outcome": "TARGET", "fixed_net_pct": "3.1"},
            {"case_id": "3", "symbol": "CCC", "market": "MX", "strategy": "BREAKOUT",
             "signal_date": "2023-01-03", "fixed_outcome": "STOP", "fixed_net_pct": "-3.5"},
        ]
        self.quality = [
            {"case_id": "1", "symbol": "AAA", "market": "US", "signal_date": "2023-01-01",
             "quality_status": "EXPERIMENTAL_COMPLETE", "quality_score": "35",
             "coverage_pct": "100", "event_risk_status": "NOT_RESEARCHED"},
            {"case_id": "2", "symbol": "BBB", "market": "US", "signal_date": "2023-01-02",
             "quality_status": "EXPERIMENTAL_COMPLETE", "quality_score": "70",
             "coverage_pct": "100", "event_risk_status": "NOT_RESEARCHED"},
            {"case_id": "3", "symbol": "CCC", "market": "MX", "signal_date": "2023-01-03",
             "quality_status": "INSUFFICIENT_COVERAGE", "quality_score": "",
             "coverage_pct": "0", "event_risk_status": "NOT_RESEARCHED"},
        ]

    def test_threshold_50(self):
        details, thresholds, summary = analyze(self.cases, self.quality)
        self.assertEqual(thresholds[2]["excluded_stop"], 1)
        self.assertEqual(thresholds[2]["excluded_target"], 0)
        self.assertEqual(thresholds[2]["unscored_stop"], 1)
        self.assertEqual(summary["sample"]["scored"], 2)
        self.assertEqual(details[2]["decision_at_50"], "UNSCORED")

    def test_threshold_boundary_retains_equal(self):
        self.quality[0]["quality_score"] = "50"
        details, _, _ = analyze(self.cases, self.quality)
        self.assertEqual(details[0]["decision_at_50"], "RETAIN")

    def test_rejects_identity_mismatch(self):
        self.quality[0]["symbol"] = "WRONG"
        with self.assertRaisesRegex(ValueError, "Identity mismatch"):
            analyze(self.cases, self.quality)

    def test_rejects_duplicate_quality(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            analyze(self.cases, self.quality + [self.quality[0]])

    def test_rejects_incomplete_with_score(self):
        self.quality[2]["quality_score"] = "0"
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            analyze(self.cases, self.quality)

    def test_rejects_invalid_outcome(self):
        self.cases[0]["fixed_outcome"] = "OPEN"
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            analyze(self.cases, self.quality)


if __name__ == "__main__":
    unittest.main()
