import unittest
from tradepilot.v6_financial_engine_cli import aggregate, TREND_COLUMNS, COVERAGE_COLUMNS

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

    def test_provider_extra_fields_do_not_break_csv_schema(self):
        import csv
        import io
        from tradepilot.v6_stop_target_cli import write_csv
        from tempfile import TemporaryDirectory
        from pathlib import Path
        cases=[case("A","ANYTHING.MX","MX")]
        trends,quality,coverage,summary=aggregate(cases,[],[])
        # MX provider rows contain provenance fields beyond the US trend schema.
        self.assertTrue(all(set(TREND_COLUMNS).issubset(set(row)) for row in trends))
        with TemporaryDirectory() as tmp:
            output=Path(tmp)/"trends.csv"
            write_csv(str(output),[{key:row.get(key,"") for key in TREND_COLUMNS} for row in trends],TREND_COLUMNS)
            with output.open(encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))),3)
        self.assertTrue(all(set(row)==set(COVERAGE_COLUMNS) for row in coverage))

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
