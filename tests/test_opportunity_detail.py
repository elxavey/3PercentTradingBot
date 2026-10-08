"""Phase 3.8: explanation is deterministic and never actionable."""
import unittest
from tradepilot.opportunity_detail import explain_opportunity


class OpportunityDetailTests(unittest.TestCase):
    def test_candidate_unconfirmed(self):
        row = {"Status": "BREAKOUT_CANDIDATE", "Confirmation": "FILTERS_NOT_MET",
               "Ranking score": 63.03, "Confirmation reasons": "VOLUME_NOT_CONFIRMED"}
        result = explain_opportunity(row, {"volume": 12})
        self.assertIn("confirmation remains separate", result["headline"])
        self.assertEqual(result["reasons"], ["VOLUME_NOT_CONFIRMED"])
        self.assertFalse(result["actionable"])

    def test_historical_pass_not_actionable(self):
        row = {"Status": "BREAKOUT_CANDIDATE",
               "Confirmation": "HISTORICAL_FILTERS_PASSED",
               "Ranking score": 95, "Confirmation reasons": ""}
        result = explain_opportunity(row)
        self.assertIn("NOT verified", result["headline"])
        self.assertFalse(result["actionable"])

    def test_insufficient_data_not_rankable(self):
        row = {"Status": "INSUFFICIENT_DATA", "Ranking score": None,
               "Reason": "STALE_COMPLETED_HISTORY"}
        result = explain_opportunity(row)
        self.assertEqual(result["components"], {})
        self.assertEqual(result["reasons"], ["STALE_COMPLETED_HISTORY"])

    def test_approaching(self):
        result = explain_opportunity({"Status": "APPROACHING", "Ranking score": 60})
        self.assertIn("near prior resistance", result["headline"])

    def test_monitoring(self):
        result = explain_opportunity({"Status": "MONITORING", "Ranking score": 30})
        self.assertIn("general monitoring", result["headline"])

    def test_components_copied(self):
        original = {"volume": 10}
        result = explain_opportunity({"Status": "APPROACHING", "Ranking score": 50}, original)
        original["volume"] = 99
        self.assertEqual(result["components"]["volume"], 10)


if __name__ == "__main__":
    unittest.main()
