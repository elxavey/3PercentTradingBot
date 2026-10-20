import unittest
from tradepilot.v6_mx_table_review_cli import research, NUMERIC


class FinancialTableReviewTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(symbol="ALSEA.MX", signal_date="2023-08-15",
                        report_period="2023-Q2", document_url="https://www.alsea.net/q2.pdf",
                        landing_url="", publication_date="2023-07-26",
                        publication_evidence="DATE_PRINTED_IN_PDF")

    def test_numeric_tokens_preserve_signed_figures(self):
        self.assertEqual(NUMERIC.findall("Ventas 12,345 -2,500 18.4%"), ["12,345", "-2,500", "18.4%"])

    def test_before_signal_can_extract_but_not_verify(self):
        rows, audit, errors = research([self.row], fetcher=lambda _: b"%PDF-test",
                                      extractor=lambda data, row, url: [{"candidate_status": "PENDING_REVIEW"}])
        self.assertEqual(rows[0]["candidate_status"], "PENDING_REVIEW")
        self.assertEqual(audit[0]["status"], "CANDIDATES_PENDING_REVIEW")
        self.assertFalse(errors)

    def test_same_day_is_excluded_without_download(self):
        row = dict(self.row, publication_date="2023-08-15")
        rows, audit, errors = research([row], fetcher=lambda _: self.fail("Downloaded post-signal"))
        self.assertEqual(rows, [])
        self.assertEqual(audit[0]["status"], "POST_SIGNAL_EXCLUDED")

    def test_missing_publication_date_blocks_download(self):
        row = dict(self.row, publication_date="")
        rows, audit, errors = research([row], fetcher=lambda _: self.fail("Downloaded undated PDF"))
        self.assertEqual(rows, [])
        self.assertEqual(audit[0]["status"], "MISSING_PUBLICATION_PROOF")


if __name__ == "__main__":
    unittest.main()
