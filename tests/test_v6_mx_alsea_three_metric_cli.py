import unittest
from tradepilot.v6_mx_alsea_three_metric_cli import build, CFO

class ThreeMetricTests(unittest.TestCase):
    def test_quarterly_cash_flow_is_ytd_difference(self):
        self.assertEqual(CFO["2023"]["H1"]-CFO["2023"]["Q1"],2482081)
        self.assertEqual(CFO["2022"]["H1"]-CFO["2022"]["Q1"],3369964)

    def test_missing_income_does_not_produce_score(self):
        rows,preview,warnings=build([])
        self.assertEqual(len(rows),2)
        self.assertTrue(all(p["status"]=="INCOMPLETE" and p["production_score"]=="" for p in preview))
        self.assertEqual(len(warnings),4)

    def test_preview_cannot_be_marked_verified(self):
        base={"symbol":"ALSEA.MX","verification_status":"PENDING_REVIEW",
              "period_latest":"2023-04-01/2023-06-30",
              "period_previous":"2022-04-01/2022-06-30",
              "currency":"MXN","scale":"UNCONFIRMED",
              "source_url":"https://www.alsea.net/report.pdf","source_page":"3"}
        comparisons=[]
        for basis in ("PRE_IFRS16","POST_IFRS16_REEXPRESSED"):
            for metric,pct in (("revenue","10.903"),("net_income","90.0")):
                comparisons.append(dict(base,basis=basis,metric=metric,
                                        latest_value="18624",previous_value="16793",
                                        calculated_change_pct=pct))
        rows,preview,warnings=build(comparisons)
        self.assertEqual(len(rows),6)
        self.assertFalse(warnings)
        self.assertTrue(all(r["verification_status"]=="PENDING_REVIEW" for r in rows))
        self.assertTrue(all(p["status"]=="ILLUSTRATIVE_ONLY_NOT_PIT_VERIFIED"
                            and p["production_score"]=="" for p in preview))

if __name__=="__main__":
    unittest.main()
