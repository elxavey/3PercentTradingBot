import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from tradepilot.risk_optimization_cli import STOPS, evaluate, risk_budget

NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)

def fake_runner(history, *, symbol, market, as_of_utc, simulation_policy):
    stop = simulation_policy.stop_pct
    trade = {"exit_reason": "STOP", "net_return_pct": -stop}
    return {"state": "RESEARCH_RESULT", "validation": {"state": "VALIDATED"},
            "backtest": {"trades": [trade],
                         "metrics": {"closed_trades": 1, "wins": 0,
                                     "average_net_return_pct": -stop}}}

class Phase47Tests(unittest.TestCase):
    def test_risk_budget_caps_planned_loss(self):
        for stop in STOPS:
            row = risk_budget(10000, 1, stop, .0025, .001)
            self.assertLessEqual(row["planned_stop_loss_mxn"], 100.01)
            self.assertTrue(row["gap_risk_unbounded"])

    def test_wider_stop_reduces_allocation(self):
        a = [risk_budget(10000, 1, stop, .0025, .001)["allocation_mxn"] for stop in STOPS]
        self.assertEqual(a, sorted(a, reverse=True))

    def test_invalid_cost_rejected(self):
        with self.assertRaises(ValueError):
            risk_budget(fee=0)

    def test_one_fetch_three_policies(self):
        fetcher = Mock(return_value=object())
        runner = Mock(side_effect=fake_runner)
        result = evaluate(["ALSEA.MX"], fee=.0025, slippage=.001,
                          fetcher=fetcher, runner=runner, as_of_utc=NOW)
        self.assertEqual(fetcher.call_count, 1)
        self.assertEqual(runner.call_count, 3)
        self.assertEqual([r["stop_pct"] for r in result["summaries"]], list(STOPS))
        self.assertIsNone(result["selected_stop"])
        self.assertFalse(result["actionable"])

    def test_failure_is_visible(self):
        def reject(*args, **kwargs):
            return {"state": "REJECT", "reasons": ["MISSING_EXCHANGE_SESSIONS"]}
        result = evaluate(["AAPL"], fee=.0025, slippage=.001,
                          fetcher=lambda *a, **k: object(),
                          runner=reject, as_of_utc=NOW)
        self.assertTrue(all(x["status"] == "REJECT"
                            for x in result["results"][0]["scenarios"]))

if __name__ == "__main__":
    unittest.main()
