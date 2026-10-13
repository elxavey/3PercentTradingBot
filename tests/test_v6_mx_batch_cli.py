import unittest
from tradepilot.v6_mx_batch_cli import batch, SYMBOLS


class MexicoBatchTests(unittest.TestCase):
    def setUp(self):
        self.cases = [
            {"case_id": f"V6-{i:03}", "symbol": symbol, "market": "MX",
             "signal_date": "2024-01-16", "fixed_outcome": "STOP" if i % 2 else "TARGET",
             "strategy": "REBOUND", "fixed_net_pct": "-3.0" if i % 2 else "3.0"}
            for i, symbol in enumerate(SYMBOLS, 1)
        ]

    def test_all_five_no_sources_remain_unscored(self):
        trends, quality, details, thresholds, coverage, summary = batch(self.cases, [])
        self.assertEqual(len(trends), 15)
        self.assertEqual(len(coverage), 5)
        self.assertEqual(summary["sample"]["scored"], 0)
        self.assertEqual(summary["sample"]["unscored"], 5)
        self.assertTrue(all(row["decision_at_50"] == "UNSCORED" for row in details))
        self.assertTrue(all(row["coverage_pct"] == 0 for row in quality))
        self.assertEqual(thresholds[2]["excluded_stop"], 0)

    def test_requires_all_five(self):
        with self.assertRaises(ValueError):
            batch(self.cases[:-1], [])

    def test_rejects_bad_source_evidence(self):
        with self.assertRaises(ValueError):
            batch(self.cases, [{"symbol": "ALSEA.MX", "metric": "revenue",
                                "verification_status": "VERIFIED",
                                "period_start": "2023-04-01",
                                "period_end": "2023-06-30",
                                "published_at": "2023-07-20",
                                "value": "10", "currency": "MXN", "scale": "1000000",
                                "source_url": "http://not-secure.example/report.pdf",
                                "source_page": "2"}])


if __name__ == "__main__":
    unittest.main()
