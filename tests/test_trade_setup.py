"""Deterministic phase 3.1 risk-engine contract tests."""
import unittest
from tradepilot.trade_setup import RiskPolicy, evaluate_setup


class SetupRiskTests(unittest.TestCase):
    def setUp(self):
        self.policy = RiskPolicy(equity=10000, risk_fraction=.005,
                                 fee_rate_per_side=.001, slippage_rate_per_side=.001)

    def evaluate(self, **overrides):
        params = dict(symbol="WALMEX.MX", market="MX", entry=50, stop=49,
                      target=52, policy=self.policy)
        params.update(overrides)
        return evaluate_setup(**params)

    def test_unknown_quote_never_actionable(self):
        r = self.evaluate()
        self.assertEqual(r["state"], "WAIT")
        self.assertFalse(r["actionable"])
        self.assertIn("LIVE_QUOTE_NOT_VERIFIED", r["reasons"])

    def test_valid_research_only_and_risk_cap(self):
        r = self.evaluate(target=52.1, quote_freshness="FRESH",
                          quote_timestamp_verified=True, instrument_verified=True)
        self.assertEqual(r["state"], "RESEARCH_READY")
        self.assertFalse(r["actionable"])
        self.assertLessEqual(r["estimated_risk"], 50)
        self.assertLessEqual(r["estimated_cash_required"], 3300)

    def test_invalid_stop_rejects(self):
        r = self.evaluate(stop=51)
        self.assertEqual(r["state"], "REJECT")
        self.assertEqual(r["quantity_research_only"], 0)

    def test_insufficient_cash_wait(self):
        r = self.evaluate(available_cash=0)
        self.assertEqual(r["quantity_research_only"], 0)
        self.assertIn("INSUFFICIENT_CAPITAL_OR_RISK_BUDGET", r["reasons"])

    def test_open_position_cap(self):
        r = self.evaluate(open_positions=3)
        self.assertIn("MAX_POSITIONS_REACHED", r["reasons"])

    def test_us_requires_fx_verification(self):
        r = self.evaluate(symbol="AMZN", market="US")
        self.assertIn("US_FX_NOT_VERIFIED", r["reasons"])

    def test_fee_drag_can_fail_reward_risk(self):
        r = self.evaluate(target=51.2)
        self.assertIn("REWARD_RISK_BELOW_MINIMUM", r["reasons"])

    def test_lot_rounding(self):
        r = self.evaluate(lot_size=10)
        self.assertEqual(r["quantity_research_only"] % 10, 0)

    def test_bad_policy_fails_closed(self):
        with self.assertRaises(ValueError):
            self.evaluate(policy=RiskPolicy(equity=-1))

    def test_missing_price_rejects(self):
        self.assertEqual(self.evaluate(entry=None)["state"], "REJECT")


if __name__ == "__main__":
    unittest.main()
