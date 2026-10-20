import unittest
from tradepilot.v6_daily_close_simulation_cli import simulate


def candidate(symbol,market="US",score="75",day="2026-10-19",status="CONFIRMED"):
    return dict(symbol=symbol,market=market,strategy="BREAKOUT",
        signal_status=status,reference_date=day,close="100",currency="USD",
        opportunity_score=score,entry="101",target="105",stop="98")


class DailyCloseTests(unittest.TestCase):
    def test_scanner_only_ranking_not_manual_symbols(self):
        rows=[candidate("ZZZ",score="40"),candidate("AAA",score="90"),
              candidate("BBB",market="MX",score="70"),candidate("CCC",status="WATCHING")]
        evaluated,selected,summary=simulate(rows,"2026-10-19",top_per_market=1)
        self.assertEqual([r["symbol"] for r in selected],["AAA","BBB"])
        self.assertEqual(summary["scanner_rows"],4)
        self.assertEqual(summary["classifications"]["WATCH"],1)

    def test_old_snapshot_abstains(self):
        _,selected,summary=simulate([candidate("AAA",day="2026-10-16")],"2026-10-19")
        self.assertEqual(selected,[])
        self.assertEqual(summary["status"],"NO_VALID_CANDIDATES")

    def test_future_data_rejected(self):
        with self.assertRaisesRegex(ValueError,"future bar"):
            simulate([candidate("AAA",day="2026-10-20")],"2026-10-19")

    def test_missing_quote_rejected(self):
        row=candidate("AAA")
        row["close"]=""
        with self.assertRaisesRegex(ValueError,"missing close"):
            simulate([row],"2026-10-19")

    def test_financial_score_cannot_change_scanner_rank(self):
        rows=[candidate("AAA",score="80"),candidate("BBB",score="70")]
        financial=[dict(symbol="AAA",market="US",quality_status="INSUFFICIENT_COVERAGE",
                        quality_score=""),
                   dict(symbol="BBB",market="US",quality_status="EXPERIMENTAL_COMPLETE",
                        quality_score="100")]
        _,selected,_=simulate(rows,"2026-10-19",financial,top_per_market=1)
        self.assertEqual(selected[0]["symbol"],"AAA")

    def test_no_synthetic_candidates(self):
        _,selected,summary=simulate([],"2026-10-19")
        self.assertEqual(selected,[])
        self.assertEqual(summary["scanner_rows"],0)

if __name__=="__main__":
    unittest.main()
