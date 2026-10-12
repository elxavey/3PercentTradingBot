import unittest
import pandas as pd
from tradepilot.historical_v5 import compare_exit_policies,aggregate_comparisons,suppress_overlapping_entries

def bars(rows):
    return pd.DataFrame(rows,index=pd.bdate_range("2026-01-05",periods=len(rows)))

class V5Tests(unittest.TestCase):
    def test_same_entry_different_exits(self):
        data=bars([
            {"Open":100,"High":101,"Low":99,"Close":100},
            {"Open":99,"High":100,"Low":96,"Close":98},
            {"Open":100,"High":105,"Low":99,"Close":104}])
        r=compare_exit_policies(data,100,94)
        self.assertEqual(r["NO_STOP"]["outcome"],"TARGET")
        self.assertEqual(r["FIXED_3PCT"]["outcome"],"STOP")
        self.assertEqual(r["STRUCTURAL"]["outcome"],"TARGET")
    def test_stop_first_same_bar(self):
        data=bars([{"Open":100,"High":101,"Low":99,"Close":100},
                   {"Open":100,"High":110,"Low":90,"Close":100}])
        r=compare_exit_policies(data,100,95)
        self.assertEqual(r["STRUCTURAL"]["outcome"],"STOP")
    def test_no_entry(self):
        r=compare_exit_policies(bars([{"Open":90,"High":95,"Low":80,"Close":90}]),100,90)
        self.assertTrue(all(v["outcome"]=="ENTRY_NOT_TRIGGERED" for v in r.values()))
    def test_gap_down_stop(self):
        data=bars([{"Open":100,"High":101,"Low":99,"Close":100},
                   {"Open":90,"High":95,"Low":85,"Close":90}])
        r=compare_exit_policies(data,100,95)
        self.assertLess(r["STRUCTURAL"]["net_pct"],-5)
    def test_nonoverlap(self):
        events=[{"symbol":"A","strategy":"BREAKOUT","signal_date":"2026-01-05",
                 "no_stop_exit_date":"2026-01-20"},
                {"symbol":"A","strategy":"BREAKOUT","signal_date":"2026-01-12"},
                {"symbol":"A","strategy":"BREAKOUT","signal_date":"2026-01-22"}]
        self.assertEqual(len(suppress_overlapping_entries(events)),2)
    def test_aggregation(self):
        event={"symbol":"A","market":"MX","strategy":"BREAKOUT","signal_date":"2026-01-05",
               "exit_comparison":{"NO_STOP":{"outcome":"TARGET","sessions_held":3},
                                  "FIXED_3PCT":{"outcome":"STOP","sessions_held":2},
                                  "STRUCTURAL":{"outcome":"OPEN_AT_LAST_BAR","sessions_held":5}}}
        r=aggregate_comparisons([event])
        self.assertEqual(r["ALL"]["policies"]["NO_STOP"]["target_pct_of_entries"],100)
        self.assertEqual(r["2026"]["policies"]["FIXED_3PCT"]["stops"],1)

if __name__=="__main__":unittest.main()
