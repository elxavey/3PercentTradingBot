"""Deterministic risk arithmetic and ranking regression tests; no network."""
import math
import unittest

from tradepilot.breakout_trade_plan import build_trade_plan
from tradepilot.morning_report import risk_diagnostics, risk_label, rebound_priority


class RiskValidationTests(unittest.TestCase):
    def make_plan(self, entry=100, stop=98):
        return build_trade_plan({"reference_close":entry,
                                 "breakout_trigger":entry,
                                 "structural_stop_reference":stop / 0.999})

    def test_net_target_includes_two_sided_costs(self):
        plan = self.make_plan()
        self.assertEqual(plan["plan_state"], "ILLUSTRATIVE_UNTRIGGERED")
        fee = plan["assumed_fee_per_side"]
        slip = plan["assumed_slippage_per_side"]
        cost = fee + slip
        entry_cost = plan["entry_reference"] * (1 + cost)
        proceeds = plan["target_exit_reference"] * (1 - cost)
        self.assertAlmostEqual((proceeds / entry_cost - 1) * 100, 3, delta=0.001)

    def test_wider_stop_reduces_reward_risk(self):
        narrow = self.make_plan(stop=98)
        wide = self.make_plan(stop=90)
        self.assertGreater(narrow["reward_risk_net"], wide["reward_risk_net"])

    def test_invalid_stop_never_actionable(self):
        plan = build_trade_plan({"reference_close":100,
                                 "breakout_trigger":100,
                                 "structural_stop_reference":110})
        self.assertEqual(plan["plan_state"], "UNAVAILABLE")
        self.assertFalse(plan["actionable"])

    def test_no_plan_cannot_pass_risk_gate(self):
        self.assertEqual(risk_label({"trade_plan": {}}), "RISK_UNAVAILABLE")

    def test_low_rr_explained(self):
        row = {"trade_plan": {"plan_state": "ILLUSTRATIVE_UNTRIGGERED",
                              "entry_reference": 100, "stop_reference": 92,
                              "reward_risk_net": 0.43}}
        self.assertEqual(risk_label(row), "UNFAVORABLE_RISK_REWARD")
        diag = risk_diagnostics(row)
        self.assertEqual(diag["distance_entry_to_stop_pct"], 8.0)
        self.assertEqual(diag["reason"], "STOP_TOO_WIDE_FOR_3_PERCENT_NET_TARGET")

    def test_confirmed_rebound_ranks_above_setup(self):
        confirmed = {"state": "REBOUND_CONFIRMED_RESEARCH", "quality_score":40, "symbol":"A"}
        setup = {"state": "REBOUND_SETUP", "quality_score":99, "symbol":"B"}
        self.assertEqual(sorted([setup, confirmed], key=rebound_priority)[0]["symbol"], "A")


if __name__ == "__main__":
    unittest.main()
