import unittest
from tradepilot.v6_mx_structured_cli import analyze, NUMBER

class StructuredTests(unittest.TestCase):
    def test_numbers_retained_for_review(self):
        self.assertGreaterEqual(len(NUMBER.findall("Ventas Netas $18,624 $16,793 10.9%")),3)

    def test_unknown_publication_not_downloaded(self):
        row=dict(symbol="ALSEA.MX",report_period="2023-Q2",signal_date="2023-08-15",
                 publication_date="",publication_evidence="",document_url="https://www.alsea.net/a.pdf",landing_url="")
        result,audit,errors=analyze([row],fetcher=lambda _: self.fail("must not download"))
        self.assertEqual(result,[])
        self.assertEqual(audit[0]["status"],"MISSING_PUBLICATION_PROOF")
        self.assertEqual(errors,[])

    def test_review_only(self):
        row=dict(symbol="ALSEA.MX",report_period="2023-Q2",signal_date="2023-08-15",
                 publication_date="2023-07-26",publication_evidence="DATE_PRINTED_IN_PDF",
                 document_url="https://www.alsea.net/a.pdf",landing_url="")
        result,audit,errors=analyze([row],fetcher=lambda _: b"%PDF-123",
            extractor=lambda data,row,url:[{"status":"PENDING_TABLE_COLUMN_VERIFICATION"}])
        self.assertEqual(result[0]["status"],"PENDING_TABLE_COLUMN_VERIFICATION")
        self.assertEqual(audit[0]["status"],"TABLE_ROWS_PENDING_REVIEW")
        self.assertFalse(errors)

if __name__=="__main__":
    unittest.main()
