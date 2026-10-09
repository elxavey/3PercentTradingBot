"""Offline regression checks for radar coverage and instrument screening."""
import unittest
from tradepilot.radar_validation_cli import summarize
from universe_discovery import is_common_equity_quote


class AuditTests(unittest.TestCase):
    def test_valid_empty_report(self):
        result = summarize({"requested":0,"results":[],"rebound_results":[],"markets":{}})
        self.assertTrue(result["passed"])

    def test_missing_rebounds_fails(self):
        result = summarize({"requested":1,"results":[{"symbol":"A","state":"REJECT"}],
                            "rebound_results":[],"markets":{}})
        self.assertIn("COVERAGE_MISMATCH",result["validation_errors"])

    def test_primary_requires_risk_and_freshness(self):
        row = {"symbol":"A","state":"CONFIRMED_RESEARCH",
               "risk_assessment":"UNFAVORABLE_RISK_REWARD",
               "session_quality":{"state":"CURRENT"}}
        result = summarize({"requested":1,"results":[row],
                            "rebound_results":[{"symbol":"A","state":"MONITORING"}],
                            "markets":{"US":{"primary":[row],"watch":[],"rebounds":{}}}})
        self.assertFalse(result["passed"])
        self.assertTrue(any(e.startswith("INVALID_PRIMARY") for e in result["validation_errors"]))

    def test_etf_rejected_and_equity_kept(self):
        self.assertFalse(is_common_equity_quote({"symbol":"NAFTRACISHRS.MX","quoteType":"EQUITY"}))
        self.assertTrue(is_common_equity_quote({"symbol":"FEMSAUBD.MX","quoteType":"EQUITY"}))


if __name__ == "__main__":
    unittest.main()
