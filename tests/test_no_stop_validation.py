import unittest
import pandas as pd
from tradepilot.no_stop_validation_cli import follow_without_stop

class NoStopTests(unittest.TestCase):
    def bars(self, rows):
        return pd.DataFrame(rows,index=pd.bdate_range("2026-01-05",periods=len(rows)))
    def test_target_on_third_session(self):
        rows=[{"Open":100,"High":101,"Low":98,"Close":99},
              {"Open":99,"High":102,"Low":94,"Close":101},
              {"Open":102,"High":105,"Low":100,"Close":104}]
        result=follow_without_stop(self.bars(rows),100)
        self.assertEqual(result["outcome"],"TARGET_3PCT_NET")
        self.assertEqual(result["sessions_to_target_including_entry"],3)
        self.assertGreater(result["max_drawdown_before_target_pct_excluding_entry_bar"],5)
    def test_not_reached_is_censored(self):
        result=follow_without_stop(self.bars([{"Open":100,"High":101,"Low":90,"Close":92}]),100)
        self.assertEqual(result["outcome"],"NOT_REACHED_BY_LAST_AVAILABLE_DATE")
        self.assertIsNone(result["sessions_to_target_including_entry"])
    def test_never_entered(self):
        result=follow_without_stop(self.bars([{"Open":95,"High":96,"Low":90,"Close":95}]),100)
        self.assertEqual(result["outcome"],"ENTRY_NOT_TRIGGERED")
    def test_gap_entry_not_trigger_price(self):
        result=follow_without_stop(self.bars([{"Open":110,"High":111,"Low":109,"Close":110}]),100)
        self.assertGreater(result["entry_price_including_slippage"],110)
    def test_no_future(self):
        result=follow_without_stop(self.bars([]),100)
        self.assertEqual(result["outcome"],"NO_FUTURE_DATA")

if __name__=="__main__":
    unittest.main()
