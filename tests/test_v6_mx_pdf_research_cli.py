import unittest
from unittest.mock import patch

from tradepilot.v6_mx_pdf_research_cli import (
    discover_pdf_links, trusted_url, run, pdf_candidates,
)


class MexicoPdfResearchTests(unittest.TestCase):
    def test_trusted_hosts_not_suffix_attack(self):
        self.assertTrue(trusted_url("https://www.alpek.com/a.pdf"))
        self.assertFalse(trusted_url("https://alpek.com.evil.org/a.pdf"))
        self.assertFalse(trusted_url("http://www.alpek.com/a.pdf"))

    def test_discover_links(self):
        html = '<a href="/reports/3t22.pdf">Report</a><a href="https://evil.org/x.pdf">No</a>'
        self.assertEqual(discover_pdf_links(html, "https://www.alpek.com/reports/"),
                         ["https://www.alpek.com/reports/3t22.pdf"])

    def test_no_auto_download_discovered_files(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return b'<a href="/2023.pdf">report</a>'
        catalog = [{"symbol": "ALSEA.MX", "official_archive": "https://www.alsea.net/inversionistas/2023.html",
                    "initial_document": ""}]
        candidates, discovered, errors = run(catalog, fetch)
        self.assertEqual(candidates, [])
        self.assertEqual(len(discovered), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(errors, [])

    def test_pdf_text_is_not_verified(self):
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF not installed")
        document = fitz.open()
        page = document.new_page()
        page.insert_text((70, 70), "Ingresos totales 120 millones")
        data = document.tobytes()
        document.close()
        result = pdf_candidates(data, "ALSEA.MX", "https://www.alsea.net/report.pdf")
        self.assertEqual(result[0]["matched_metric"], "revenue")
        self.assertEqual(result[0]["verification_status"], "PENDING_REVIEW")
        self.assertEqual(result[0]["page"], 1)


if __name__ == "__main__":
    unittest.main()
