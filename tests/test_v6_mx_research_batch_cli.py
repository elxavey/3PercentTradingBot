import unittest
from tradepilot.v6_mx_research_batch_cli import SYMBOLS, ARCHIVES, targeted_links, research


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

    def test_missing_pdf_is_not_verified(self):
        def fake_fetch(url):
            return b"<html><a href='/other-2025.pdf'>2025</a></html>"
        leads, discovered, errors = research(fetcher=fake_fetch)
        self.assertEqual(leads, [])
        self.assertEqual(len(errors), 5)
        self.assertTrue(all(row["status"] == "DISCOVERED_ONLY" for row in discovered))


if __name__ == "__main__":
    unittest.main()
