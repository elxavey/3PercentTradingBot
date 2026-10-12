import unittest
from tradepilot.breakout_trade_plan import build_trade_plan
from tradepilot.risk_diagnostics import diagnose_risk, compare_cost_scenarios, aggregate_risk_diagnostics

class RiskDiagnosticsTests(unittest.TestCase):
    def plan(self, stop):
        return build_trade_plan({"reference_close":100,"breakout_trigger":101,"structural_stop_reference":stop})
    def test_wide_stop(self):
        self.assertEqual(diagnose_risk(self.plan(90))["status"],"FAIL")
    def test_tight_stop(self):
        self.assertEqual(diagnose_risk(self.plan(99))["status"],"PASS")
    def test_scenarios(self):
        p=self.plan(95)
        result=compare_cost_scenarios(p)
        self.assertEqual(len(result),3)
        self.assertEqual(p["assumed_fee_per_side"],0.0025)
    def test_stop_unchanged(self):
        p=self.plan(90)
        diagnose_risk(p)
        self.assertEqual(p["stop_reference"],89.91)
    def test_invalid(self):
        self.assertEqual(diagnose_risk({})["status"],"UNAVAILABLE")
    def test_aggregate(self):
        e={"market":"US","strategy":"BREAKOUT","risk_diagnostic":diagnose_risk(self.plan(90))}
        self.assertEqual(aggregate_risk_diagnostics([e])["US_BREAKOUT"]["failed"],1)

if __name__=="__main__":
    unittest.main()
