import unittest
from tradepilot.v6_mx_alsea_comparison_cli import parse

HEAD="Pre-IFRS16 Post-IFRS16 + Reexpresión Argentina | 2T23 2T22 Var % 2T23 2T22 Var %"
def sample(metric,text,header=HEAD):
    return dict(symbol="ALSEA.MX",metric=metric,table_row=text,header_context=header,
                source_url="https://www.alsea.net/q2.pdf",page="3",
                published_at="2023-07-26",signal_date="2023-08-15")

class AlseaComparisonTests(unittest.TestCase):
    def test_separates_ifrs_bases_and_deduplicates(self):
        row=sample("revenue","Ventas Netas $18,624 $16,793 10.9% $18,949 $16,939 11.9%")
        candidates,audit=parse([row,row])
        self.assertEqual(len(candidates),2)
        self.assertEqual([(x["basis"],x["latest_value"],x["previous_value"]) for x in candidates],
                         [("PRE_IFRS16",18624,16793),("POST_IFRS16_REEXPRESSED",18949,16939)])
        self.assertEqual(sum(x["status"]=="DUPLICATE" for x in audit),2)
        self.assertTrue(all(x["verification_status"]=="PENDING_REVIEW" for x in candidates))

    def test_income_and_missing_cfo(self):
        candidates,audit=parse([sample("net_income","Utilidad Neta $475 $250 89.7% $490 $237 106.9%")])
        self.assertEqual(len(candidates),2)
        self.assertEqual(candidates[0]["calculated_change_pct"],90.0)
        self.assertEqual(candidates[0]["verification_status"],"PENDING_REVIEW")
        self.assertTrue(any(x["metric"]=="operating_cash_flow" and x["status"]=="MISSING_SOURCE" for x in audit))

    def test_no_narrative_or_missing_headers(self):
        rows=[sample("revenue","Ventas Netas 2T23 vs. 2T22"),
              sample("revenue","Ventas Netas $18,624 $16,793 10.9% $18,949 $16,939 11.9%","")]
        candidates,audit=parse(rows)
        self.assertFalse(candidates)
        self.assertTrue(any(x["status"]=="BLOCKED" for x in audit))

    def test_post_signal_never_accepted(self):
        row=sample("revenue","Ventas Netas $18,624 $16,793 10.9% $18,949 $16,939 11.9%")
        row["published_at"]="2023-08-15"
        candidates,audit=parse([row])
        self.assertFalse(candidates)
        self.assertTrue(any(x["status"]=="BLOCKED" for x in audit))

if __name__=="__main__":
    unittest.main()
