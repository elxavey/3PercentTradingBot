import unittest
from tradepilot.v6_alpek_cashflow import YTD, operating_cash_flow_rows, evidence_details


class AlpekCashFlowTests(unittest.TestCase):
    def test_quarter_is_nine_month_less_six_month(self):
        rows = {int(r["period_end"][:4]): r for r in operating_cash_flow_rows()}
        self.assertEqual(int(rows[2022]["value"]), 2543)
        self.assertEqual(int(rows[2021]["value"]), 623)
        self.assertEqual(9948 - 7405, 2543)
        self.assertEqual(7378 - 6755, 623)

    def test_source_and_date_caveat_preserved(self):
        evidence = evidence_details()
        self.assertEqual(evidence["statement_page"], 3)
        self.assertIn("not a confirmed filing date", evidence["publication_date_caveat"])
        self.assertIn("2022/11", evidence["nine_month_source"])
        self.assertIn("2022/08", evidence["six_month_source"])


if __name__ == "__main__":
    unittest.main()
