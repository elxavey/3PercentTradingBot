"""Offline tests for SEC companyfacts point-in-time extraction."""
import unittest
from tradepilot.v6_sec_fundamentals_cli import select_fact, analyze, cik_mapping


class FundamentalsTests(unittest.TestCase):
    def setUp(self):
        self.facts = {"cik": 1234, "facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [
                {"start": "2022-10-01", "end": "2022-12-31",
                 "filed": "2023-01-31", "form": "10-Q", "val": 100,
                 "accn": "0001234-23-000001"},
                {"start": "2022-10-01", "end": "2022-12-31",
                 "filed": "2023-02-01", "form": "10-Q", "val": 999},
                {"start": "2023-01-01", "end": "2023-03-31",
                 "filed": "2023-04-15", "form": "10-Q", "val": 200},
            ]}},
            "Assets": {"units": {"USD": [
                {"end": "2022-12-31", "filed": "2023-01-31",
                 "form": "10-Q", "val": 500}
            ]}},
        }}}

    def test_strict_filing_cutoff(self):
        row = select_fact(self.facts, "revenue", "2023-02-01")
        self.assertEqual(row["value"], 100)
        self.assertEqual(row["filed"], "2023-01-31")

    def test_no_future_or_same_day_facts(self):
        self.assertIsNone(select_fact(self.facts, "revenue", "2023-01-31"))

    def test_instant_asset_fact(self):
        self.assertEqual(select_fact(self.facts, "assets", "2023-02-01")["value"], 500)

    def test_analysis_skips_mexico(self):
        cases = [{"case_id": "V6-1", "symbol": "ABC", "market": "US",
                  "signal_date": "2023-02-01"},
                 {"case_id": "V6-2", "symbol": "ALSEA.MX", "market": "MX",
                  "signal_date": "2023-02-01"}]
        rows, errors = analyze(cases, {"ABC": 1234}, lambda _: self.facts)
        self.assertFalse(errors)
        self.assertEqual({r["metric"] for r in rows}, {"revenue", "assets"})
        self.assertTrue(all(r["symbol"] == "ABC" for r in rows))

    def test_ticker_mapping(self):
        self.assertEqual(cik_mapping({"0": {"ticker": "abc", "cik_str": 1234}}), {"ABC": 1234})


if __name__ == "__main__":
    unittest.main()
