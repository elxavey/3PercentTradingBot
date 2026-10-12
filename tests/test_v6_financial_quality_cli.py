import unittest
from tradepilot.v6_financial_quality_cli import metric_signal, score_cases


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.case = {"case_id": "V6-1", "symbol": "ABC", "market": "US",
                     "signal_date": "2023-02-01"}

    def trend(self, metric, previous, latest):
        return {"case_id": "V6-1", "symbol": "ABC", "signal_date": "2023-02-01",
                "metric": metric, "previous_value": str(previous),
                "latest_value": str(latest), "status": "CANDIDATE_YOY",
                "previous_filed": "2022-02-01", "latest_filed": "2023-01-31"}

    def test_complete_quality_score(self):
        rows = [self.trend("revenue", 100, 120),
                self.trend("net_income", -20, 10),
                self.trend("operating_cash_flow", 10, -10)]
        result = score_cases([self.case], rows)[0]
        self.assertEqual(result["quality_score"], 70)
        self.assertEqual(result["coverage_pct"], 100)
        self.assertEqual(result["event_risk_status"], "NOT_RESEARCHED")

    def test_missing_not_negative(self):
        result = score_cases([self.case], [self.trend("revenue", 100, 120)])[0]
        self.assertEqual(result["quality_score"], "")
        self.assertEqual(result["coverage_pct"], 35)
        self.assertEqual(result["net_income_signal"], "MISSING")

    def test_negative_base_improvement(self):
        value, reason = metric_signal(self.trend("operating_cash_flow", -100, -20))
        self.assertEqual(value, 1)
        self.assertEqual(reason, "NEGATIVE_BASE_COMPARISON")

    def test_point_in_time_guard(self):
        row = self.trend("revenue", 100, 120)
        row["latest_filed"] = "2023-02-01"
        with self.assertRaisesRegex(ValueError, "Point-in-time"):
            score_cases([self.case], [row])

    def test_duplicate_guard(self):
        row = self.trend("revenue", 100, 120)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            score_cases([self.case], [row, row])

    def test_identity_guard(self):
        row = self.trend("revenue", 100, 120)
        row["symbol"] = "XYZ"
        with self.assertRaisesRegex(ValueError, "identity"):
            score_cases([self.case], [row])


if __name__ == "__main__":
    unittest.main()
