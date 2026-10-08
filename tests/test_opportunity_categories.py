"""Presentation categories must not conflate ranking with confirmation."""
import unittest
from tradepilot.opportunity_categories import research_category, CATEGORY_ORDER


class ResearchCategoryTests(unittest.TestCase):
    def test_historical_confirmed(self):
        self.assertEqual(research_category("BREAKOUT_CANDIDATE", "HISTORICAL_FILTERS_PASSED"), "Historical confirmed")

    def test_unconfirmed_candidate(self):
        self.assertEqual(research_category("BREAKOUT_CANDIDATE", "FILTERS_NOT_MET"), "Breakout watch")

    def test_approaching(self):
        self.assertEqual(research_category("APPROACHING", "HISTORICAL_FILTERS_PASSED"), "Near resistance")

    def test_monitoring(self):
        self.assertEqual(research_category("MONITORING", "FILTERS_NOT_MET"), "General monitoring")

    def test_missing_data(self):
        self.assertEqual(research_category("INSUFFICIENT_DATA", None), "Excluded — unverified data")

    def test_unknown_fails_closed(self):
        self.assertEqual(research_category("UNKNOWN", None), "Excluded — unverified data")

    def test_categories_unique(self):
        self.assertEqual(len(CATEGORY_ORDER), len(set(CATEGORY_ORDER)))


if __name__ == "__main__":
    unittest.main()
