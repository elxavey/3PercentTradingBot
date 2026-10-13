import unittest
from tradepilot.v6_mx_research_batch_cli import SYMBOLS, ARCHIVES, targeted_links, research, crawl_pdfs


class MexicoResearchBatchTests(unittest.TestCase):
    def test_targeted_filter_never_downloads_every_pdf(self):
        urls = [
            "https://www.pinfra.com.mx/reports/3T22.pdf",
            "https://www.pinfra.com.mx/reports/4T25.pdf",
            "https://www.pinfra.com.mx/reports/3T22-extra.pdf",
        ]
        self.assertEqual(targeted_links("PINFRA.MX", urls, 1), urls[:1])

    def test_official_sources_cover_all_five(self):
        self.assertEqual(set(ARCHIVES), set(SYMBOLS))
        self.assertTrue(all(u.startswith("https://") for u in ARCHIVES.values()))

    def test_follows_official_archive_subpage_only(self):
        start = "https://www.alsea.net/inversionistas/2023.html"
        sub = "https://www.alsea.net/inversionistas/reportes-2023.html"
        def fake_fetch(url):
            if url == start:
                return b'<a href="reportes-2023.html">Reports</a><a href="https://evil.example/investors">evil</a>'
            if url == sub:
                return b'<a href="/files/Alsea-2T23.pdf">quarter</a>'
            raise AssertionError("unexpected fetch: " + url)
        urls, errors = crawl_pdfs("ALSEA.MX", start, fake_fetch)
        self.assertEqual(errors, [])
        self.assertEqual(urls, ["https://www.alsea.net/files/Alsea-2T23.pdf"])

    def test_missing_pdf_is_not_verified(self):
        def fake_fetch(url):
            return b"<html><a href='/other-2025.pdf'>2025</a></html>"
        leads, discovered, errors = research(fetcher=fake_fetch)
        self.assertEqual(leads, [])
        self.assertEqual(len(errors), 5)
        self.assertTrue(all(row["status"] == "DISCOVERED_ONLY" for row in discovered))


if __name__ == "__main__":
    unittest.main()
