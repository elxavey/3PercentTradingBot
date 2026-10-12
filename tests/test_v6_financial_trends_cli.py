import unittest
from tradepilot.v6_financial_trends_cli import compare, build


def fact(start, end, filed, value):
    return {"start": start, "end": end, "filed": filed, "val": value, "form": "10-Q"}


class TrendsTests(unittest.TestCase):
    def setUp(self):
        self.payload = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            fact("2021-10-01", "2021-12-31", "2022-02-01", 80),
            fact("2022-10-01", "2022-12-31", "2023-01-25", 100),
            fact("2022-10-01", "2022-12-31", "2023-02-01", 999),
        ]}}}}}

    def test_yoy_prior_day_only(self):
        result = compare(self.payload, "revenue", "2023-02-01")
        self.assertEqual(result["status"], "CANDIDATE_YOY")
        self.assertEqual(result["change_pct"], 25.0)
        self.assertEqual(result["latest_value"], 100)

    def test_missing_prior_year(self):
        result = compare(self.payload, "revenue", "2022-02-02")
        self.assertEqual(result["status"], "MISSING_YOY_COMPARISON")

    def test_missing_metric(self):
        self.assertEqual(compare(self.payload, "net_income", "2023-02-01")["status"],
                         "MISSING_LATEST")

    def test_zero_baseline(self):
        self.payload["facts"]["us-gaap"]["Revenues"]["units"]["USD"][0]["val"] = 0
        self.assertEqual(compare(self.payload, "revenue", "2023-02-01")["status"],
                         "ZERO_BASELINE")

    def test_mx_skipped(self):
        rows, errors = build([{"case_id": "1", "symbol": "ALSEA.MX",
                               "market": "MX", "signal_date": "2023-02-01"}],
                             {}, lambda _: self.payload)
        self.assertEqual(rows, [])
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
