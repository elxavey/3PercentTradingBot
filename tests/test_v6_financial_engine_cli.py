import unittest
from tradepilot.v6_financial_engine_cli import aggregate

def case(cid,symbol,market):
    return dict(case_id=cid,symbol=symbol,market=market,signal_date="2023-08-15")

class GenericEngineTests(unittest.TestCase):
    def test_arbitrary_symbols_without_allowlist(self):
        cases=[case("A","ANYTHING.MX","MX"),case("B","CUSTOM","US")]
        trends,quality,coverage,summary=aggregate(cases,[],[])
        self.assertEqual(len(trends),6)
        self.assertEqual(len(quality),2)
        self.assertEqual(summary["quality_status"]["INSUFFICIENT_COVERAGE"],2)
        self.assertEqual({r["status"] for r in coverage},{"MISSING_LATEST","MISSING_PROVIDER_DATA"})

    def test_identity_guard(self):
        with self.assertRaisesRegex(ValueError,"identity mismatch"):
            aggregate([case("B","CUSTOM","US")],
                      [dict(case_id="B",symbol="OTHER",signal_date="2023-08-15",metric="revenue")],[])

    def test_duplicate_cases(self):
        with self.assertRaisesRegex(ValueError,"Duplicate case_id"):
            aggregate([case("A","AAA","MX"),case("A","BBB","US")],[],[])

    def test_invalid_market(self):
        with self.assertRaisesRegex(ValueError,"Unsupported market"):
            aggregate([case("A","AAA","CA")],[],[])

if __name__=="__main__":
    unittest.main()
