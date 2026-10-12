"""Offline tests for historical SEC filing discovery."""
import unittest
from tradepilot.v6_sec_discovery_cli import discover, resolve_ciks, SEC_SUBMISSIONS


class SECDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.cases = [{"case_id": "V6-001", "symbol": "PLTR", "market": "US",
                       "signal_date": "2023-02-01"},
                      {"case_id": "V6-002", "symbol": "ALSEA.MX", "market": "MX",
                       "signal_date": "2023-02-01"}]
        self.tickers = {"0": {"ticker": "PLTR", "cik_str": 1321655}}
        self.filings = {"name": "Example Company", "filings": {"recent": {
            "form": ["8-K", "10-Q", "8-K", "10-K"],
            "filingDate": ["2023-01-31", "2023-02-01", "2023-02-01", "2023-02-02"],
            "acceptanceDateTime": ["2023-01-31T14:00:00",
                                   "2023-02-01T15:00:00",
                                   "2023-02-01T17:00:00",
                                   "2023-02-02T10:00:00"],
            "accessionNumber": ["0001321655-23-000001", "0001321655-23-000002",
                                "0001321655-23-000003", "0001321655-23-000004"],
            "primaryDocument": ["report.htm"] * 4,
        }}}

    def test_only_filing_accepted_before_market_close(self):
        def fetch(url):
            self.assertEqual(url, SEC_SUBMISSIONS.format(cik=1321655))
            return self.filings
        rows, errors = discover(self.cases, self.tickers, fetch)
        self.assertFalse(errors)
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["form"] for r in rows}, {"8-K", "10-Q"})
        self.assertTrue(all(r["research_status"] == "CANDIDATE_NOT_REVIEWED" for r in rows))

    def test_missing_acceptance_excludes_same_day(self):
        self.filings["filings"]["recent"]["acceptanceDateTime"][1] = ""
        rows, _ = discover(self.cases, self.tickers, lambda _: self.filings)
        self.assertEqual(len(rows), 1)

    def test_cik_mapping(self):
        self.assertEqual(resolve_ciks(self.tickers)["PLTR"], 1321655)

    def test_missing_ticker_is_reported(self):
        rows, errors = discover(self.cases, {}, lambda _: self.filings)
        self.assertFalse(rows)
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
