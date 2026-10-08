"""Phase 3.7 ranking tests: deterministic, fail-closed, research only."""
import unittest
from tradepilot.opportunity_ranking import rank_opportunity, rank_watchlist


def opportunity(state="APPROACHING", distance=1.0):
    return {"state": state, "distance_pct": distance}


def confirmation(state="FILTERS_NOT_MET", ratio=1.2, closes=1, required=2,
                 trend=True, volume=True, persistence=False):
    return {"state": state, "volume_ratio": ratio,
            "confirmed_closes": closes, "required_closes": required,
            "checks": {"trend": trend, "volume": volume,
                       "persistence": persistence}}


class OpportunityRankingTests(unittest.TestCase):
    def rank(self, o=None, c=None, evidence="LATEST_COMPLETED_SESSION"):
        return rank_opportunity(o if o is not None else opportunity(),
                                c if c is not None else confirmation(),
                                history_evidence=evidence)

    def test_score_bounded_and_non_actionable(self):
        result = self.rank()
        self.assertTrue(result["eligible"])
        self.assertGreaterEqual(result["ranking_score"], 0)
        self.assertLessEqual(result["ranking_score"], 100)
        self.assertFalse(result["actionable"])
        self.assertEqual(sum(result["components"].values()), result["ranking_score"])

    def test_stale_excluded(self):
        result = self.rank(evidence="OLDER_COMPLETED_SESSION")
        self.assertIsNone(result["ranking_score"])
        self.assertFalse(result["eligible"])

    def test_insufficient_excluded(self):
        result = self.rank(o=opportunity("INSUFFICIENT_DATA"))
        self.assertIsNone(result["ranking_score"])

    def test_confirmation_missing_excluded(self):
        result = self.rank(c={"state": "INSUFFICIENT_DATA"})
        self.assertIsNone(result["ranking_score"])

    def test_nan_excluded(self):
        result = self.rank(o=opportunity(distance=float("nan")))
        self.assertIsNone(result["ranking_score"])

    def test_candidate_not_confirmed_by_score(self):
        result = self.rank(o=opportunity("BREAKOUT_CANDIDATE", -0.1))
        self.assertEqual(result["ranking_tier"], "UNCONFIRMED_BREAKOUT")
        self.assertFalse(result["actionable"])

    def test_historical_pass_still_not_actionable(self):
        result = self.rank(o=opportunity("BREAKOUT_CANDIDATE", -0.1),
                           c=confirmation(state="HISTORICAL_FILTERS_PASSED",
                                          closes=2, persistence=True))
        self.assertEqual(result["ranking_tier"], "HISTORICAL_FILTERS_PASSED")
        self.assertFalse(result["actionable"])

    def test_volume_and_trend_increase_score(self):
        strong = self.rank()
        weak = self.rank(c=confirmation(ratio=0.3, trend=False))
        self.assertGreater(strong["ranking_score"], weak["ranking_score"])

    def test_deterministic_sort_and_exclusions_last(self):
        rows = [{"symbol": "B", "ranking_score": 70},
                {"symbol": "X", "ranking_score": None},
                {"symbol": "A", "ranking_score": 70},
                {"symbol": "C", "ranking_score": 40}]
        self.assertEqual([r["symbol"] for r in rank_watchlist(rows)],
                         ["A", "B", "C", "X"])


if __name__ == "__main__":
    unittest.main()
