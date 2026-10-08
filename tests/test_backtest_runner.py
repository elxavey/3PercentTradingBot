import unittest
from unittest.mock import patch
import pandas as pd
from tradepilot.backtest_runner import performance_metrics, run_backtest


def bars(n=30):
    return pd.DataFrame({"Open":[100.]*n,"High":[101.]*n,"Low":[99.]*n,
                         "Close":[100.]*n,"Volume":[1000.]*n},
                        index=pd.bdate_range("2026-01-05",periods=n))


def trade(value, age=2):
    return {"simulated":True,"net_return_pct":value,"holding_sessions":age}


class BacktestRunnerTests(unittest.TestCase):
    def test_empty_metrics_are_not_fabricated(self):
        m = performance_metrics([])
        self.assertEqual(m["closed_trades"],0)
        self.assertIsNone(m["win_rate_pct"])
        self.assertIsNone(m["compounded_net_return_pct"])

    def test_win_loss_compound_drawdown(self):
        m = performance_metrics([trade(10),trade(-10),trade(0)])
        self.assertEqual((m["wins"],m["losses"],m["breakeven"]),(1,1,1))
        self.assertAlmostEqual(m["win_rate_pct"],33.3333)
        self.assertAlmostEqual(m["compounded_net_return_pct"],-1)
        self.assertAlmostEqual(m["max_closed_trade_drawdown_pct"],10)
        self.assertAlmostEqual(m["profit_factor"],1)
        self.assertEqual(m["average_holding_sessions"],2)

    def test_all_winners_no_infinite_profit_factor(self):
        m = performance_metrics([trade(3),trade(4)])
        self.assertIsNone(m["profit_factor"])
        self.assertIsNone(m["average_loss_pct"])

    def test_invalid_returns_rejected(self):
        for value in (float("nan"),float("inf"),-100):
            with self.subTest(value=value),self.assertRaises(ValueError):
                performance_metrics([trade(value)])

    def test_integrates_real_replay_with_no_confirmations(self):
        r = run_backtest(bars(),symbol="TEST",market="MX")
        self.assertEqual(r["confirmed_signal_sessions"],0)
        self.assertEqual(r["metrics"]["closed_trades"],0)
        self.assertEqual(r["currency"],"MXN")
        self.assertFalse(r["actionable"])

    def test_replay_confirmed_signal_flows_to_simulator(self):
        h = bars()
        h.iloc[24,h.columns.get_loc("High")] = 105
        h.iloc[24,h.columns.get_loc("Close")] = 104
        event = {"session":h.index[23].date().isoformat(),
                 "confirmation":"HISTORICAL_FILTERS_PASSED"}
        fake = {"events":[event],"evaluated_sessions":1}
        with patch("tradepilot.backtest_runner.replay_signals",return_value=fake):
            r = run_backtest(h,symbol="TEST",market="US")
        self.assertEqual(r["confirmed_signal_sessions"],1)
        self.assertEqual(r["metrics"]["closed_trades"],1)
        self.assertEqual(r["trades"][0]["entry_session"],h.index[24].date().isoformat())

    def test_invalid_market_rejected(self):
        with self.assertRaises(ValueError):
            run_backtest(bars(),symbol="TEST",market="UNKNOWN")


if __name__ == "__main__":
    unittest.main()
