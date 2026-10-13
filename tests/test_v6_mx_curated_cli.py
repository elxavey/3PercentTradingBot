import unittest
from tradepilot.v6_mx_curated_cli import resolve_document, audit


class CuratedSourceTests(unittest.TestCase):
    def test_resolves_unique_results_pdf(self):
        row = {"document_url": "", "landing_url": "https://grupobimbo.com/en/investors/events/3q23"}
        def fetcher(url):
            return b'<a href="/docs/report.pdf" title="Results Report">PDF</a>'
        self.assertEqual(resolve_document(row, fetcher)[0], "https://grupobimbo.com/docs/report.pdf")

    def test_ambiguous_pdf_never_auto_selected(self):
        row = {"document_url": "", "landing_url": "https://grupobimbo.com/en/investors/events/3q23"}
        def fetcher(url):
            return b'<a href="/a.pdf" title="Results Report">A</a><a href="/b.pdf" title="Results Report">B</a>'
        self.assertEqual(resolve_document(row, fetcher)[1], "AMBIGUOUS_DOCUMENT_LINK")

    def test_post_signal_source_not_downloaded(self):
        row = dict(symbol="ALSEA.MX", signal_date="2023-08-15",
                   report_period="2023-Q2", document_url="https://www.alsea.net/test.pdf",
                   landing_url="", publication_date="2023-08-16",
                   publication_evidence="DATE_PRINTED_IN_PDF", review_status="PENDING_NUMERIC_REVIEW",
                   notes="")
        documents, leads, errors = audit([row], fetcher=lambda url: (_ for _ in ()).throw(AssertionError("downloaded")))
        self.assertEqual(documents[0]["status"], "POST_SIGNAL_EXCLUDED")
        self.assertEqual(leads, [])
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
