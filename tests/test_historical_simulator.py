import unittest
import pandas as pd
from tradepilot.historical_simulator import SimulationPolicy, simulate_trades

def bars(rows):
    return pd.DataFrame(rows, columns=["Open","High","Low","Close","Volume"],
                        index=pd.bdate_range("2026-01-05", periods=len(rows)))

def signal(day):
    return {"events":[{"session":day,"confirmation":"HISTORICAL_FILTERS_PASSED"}]}

class HistoricalSimulatorTests(unittest.TestCase):
    def test_next_session_entry_and_target(self):
        h = bars([(100,101,99,100,1000),(100,101,99,100,1000),
                  (100,105,99,104,1000)])
        result = simulate_trades(h, signal("2026-01-06"))
        t = result["trades"][0]
        self.assertEqual(t["entry_session"], "2026-01-07")
        self.assertEqual(t["exit_reason"], "TARGET")
        self.assertAlmostEqual(t["net_return_pct"], 3.6)

    def test_same_bar_both_hit_stop_first(self):
        h = bars([(100,101,99,100,1000),(100,101,99,100,1000),
                  (100,105,97,100,1000)])
        t = simulate_trades(h, signal("2026-01-06"))["trades"][0]
        self.assertEqual(t["exit_reason"], "STOP_FIRST_AMBIGUOUS")
        self.assertAlmostEqual(t["net_return_pct"], -1.8)

    def test_gap_through_stop(self):
        h = bars([(100,101,99,100,1000),(100,101,99,100,1000),
                  (95,96,93,94,1000)])
        t = simulate_trades(h, signal("2026-01-06"))["trades"][0]
        self.assertEqual(t["exit_reason"], "STOP")
        self.assertAlmostEqual(t["entry_price"], 95)

    def test_costs_reduce_net(self):
        h = bars([(100,101,99,100,1000),(100,101,99,100,1000),
                  (100,105,99,104,1000)])
        p = SimulationPolicy(fee_rate_per_side=.001,slippage_rate_per_side=.001)
        t = simulate_trades(h, signal("2026-01-06"), policy=p)["trades"][0]
        self.assertLess(t["net_return_pct"], t["gross_return_pct_after_slippage"])

    def test_time_exit(self):
        h = bars([(100,101,99,100,1000),(100,101,99,100,1000),
                  (100,101,99,100,1000),(100,101,99,100,1000)])
        p = SimulationPolicy(max_holding_sessions=2)
        t = simulate_trades(h, signal("2026-01-06"),policy=p)["trades"][0]
        self.assertEqual(t["exit_reason"], "TIME_EXIT")
        self.assertEqual(t["holding_sessions"], 2)

    def test_open_at_end_not_counted(self):
        h = bars([(100,101,99,100,1000),(100,101,99,100,1000),
                  (100,101,99,100,1000)])
        r = simulate_trades(h, signal("2026-01-06"))
        self.assertEqual(r["closed_trades"], 0)
        self.assertTrue(r["open_at_end_excluded"])

    def test_no_same_day_signal_entry(self):
        h = bars([(100,101,99,100,1000),(100,105,99,104,1000)])
        r = simulate_trades(h, signal("2026-01-06"))
        self.assertEqual(r["closed_trades"], 0)

    def test_invalid_policy(self):
        with self.assertRaises(ValueError):
            SimulationPolicy(max_holding_sessions=0)

if __name__ == "__main__":
    unittest.main()
