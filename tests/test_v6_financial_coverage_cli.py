import unittest
from tradepilot.v6_financial_coverage_cli import audit, METRICS


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.cases = [
            {"case_id": "V6-1", "symbol": "AI", "market": "US", "signal_date": "2023-02-01"},
            {"case_id": "V6-2", "symbol": "ALSEA.MX", "market": "MX", "signal_date": "2023-02-01"},
        ]

    def test_missing_is_not_risk(self):
        rows = audit(self.cases, [])
        self.assertEqual(len(rows), 2 * len(METRICS))
        self.assertEqual(rows[0]["coverage_status"], "MISSING_FACT")
        self.assertEqual(rows[len(METRICS)]["coverage_status"], "NOT_SUPPORTED_MX")

    def test_fact_age(self):
        rows = audit(self.cases, [{"case_id": "V6-1", "metric": "revenue",
            "value": "100", "unit": "USD", "filed": "2023-01-20",
            "period_end": "2022-12-31", "source_url": "https://www.sec.gov/"}])
        self.assertEqual(rows[0]["coverage_status"], "CANDIDATE")
        self.assertEqual(rows[0]["days_old_at_signal"], 32)

    def test_errors_and_duplicates(self):
        rows = audit(self.cases, [], ["AI: HTTPError"])
        self.assertEqual(rows[0]["coverage_status"], "SOURCE_ERROR")
        facts = [{"case_id": "V6-1", "metric": "cash"}] * 2
        rows = audit(self.cases, facts)
        self.assertEqual(rows[4]["coverage_status"], "DUPLICATE_FACT")


if __name__ == "__main__":
    unittest.main()
