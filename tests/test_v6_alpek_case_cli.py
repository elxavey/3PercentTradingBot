import csv
import unittest
from pathlib import Path
from tradepilot.v6_alpek_case_cli import run


class AlpekCaseTests(unittest.TestCase):
    def test_official_observations_are_partial_not_fabricated(self):
        with Path("research/v6_alpek_verified_observations.csv").open(
                newline="", encoding="utf-8") as stream:
            observations = list(csv.DictReader(stream))
        case = {"case_id": "V6-002", "symbol": "ALPEKA.MX", "market": "MX",
                "signal_date": "2022-12-20", "fixed_outcome": "STOP",
                "strategy": "BREAKOUT", "fixed_net_pct": "-3.0"}
        trends, quality, details, _, summary = run([case], observations)
        by_metric = {r["metric"]: r for r in trends}
        self.assertAlmostEqual(float(by_metric["revenue"]["change_pct"]), 43.451, places=2)
        self.assertAlmostEqual(float(by_metric["net_income"]["change_pct"]), -5.581, places=2)
        self.assertEqual(by_metric["operating_cash_flow"]["status"], "MISSING_LATEST")
        self.assertEqual(quality[0]["coverage_pct"], 70)
        self.assertEqual(quality[0]["quality_score"], "")
        self.assertEqual(details[0]["decision_at_50"], "UNSCORED")
        self.assertEqual(summary["sample"]["unscored"], 1)

    def test_signal_before_publication_no_leak(self):
        with Path("research/v6_alpek_verified_observations.csv").open(
                newline="", encoding="utf-8") as stream:
            observations = list(csv.DictReader(stream))
        case = {"case_id": "V6-002", "symbol": "ALPEKA.MX", "market": "MX",
                "signal_date": "2022-10-20", "fixed_outcome": "STOP",
                "strategy": "BREAKOUT", "fixed_net_pct": "-3.0"}
        trends, quality, _, _, _ = run([case], observations)
        self.assertTrue(all(r["status"] == "MISSING_LATEST" for r in trends))
        self.assertEqual(quality[0]["coverage_pct"], 0)


if __name__ == "__main__":
    unittest.main()
