import unittest
import pandas as pd
from tradepilot.historical_replay import replay_signals

def sample(n=50):
    dates = pd.bdate_range("2026-01-05", periods=n)
    return pd.DataFrame({"Open":[100.0]*n,"High":[101.0]*n,
                         "Low":[99.0]*n,"Close":[100.0]*n,
                         "Volume":[1000.0]*n},index=dates)

class HistoricalReplayTests(unittest.TestCase):
    def test_warmup_and_count(self):
        result = replay_signals(sample(), symbol="TEST", market="US")
        self.assertEqual(result["warmup_sessions"], 22)
        self.assertEqual(result["evaluated_sessions"], 29)
        self.assertTrue(all(not e["actionable"] for e in result["events"]))

    def test_future_bars_do_not_change_prior_events(self):
        history = sample()
        first = replay_signals(history.iloc[:35], symbol="TEST", market="US")
        history.iloc[35:, history.columns.get_loc("Close")] = 105
        later = replay_signals(history, symbol="TEST", market="US")
        self.assertEqual(first["events"], later["events"][:len(first["events"])])

    def test_insufficient_history(self):
        result = replay_signals(sample(20), symbol="TEST", market="MX")
        self.assertEqual(result["events"], [])

    def test_invalid_index_rejected(self):
        with self.assertRaises(ValueError):
            replay_signals(sample().iloc[::-1], symbol="TEST", market="US")

if __name__ == "__main__":
    unittest.main()
