"""Regression checks for the scanner-to-original-engine bridge."""
import unittest
from unittest.mock import patch

from tradepilot.v6_original_engine_cli import evaluate
from tradepilot.v6_selected_history_refresh_cli import refresh


class OriginalEngineTests(unittest.TestCase):
    @patch("tradepilot.v6_original_engine_cli.report")
    def test_preclose_run_does_not_evaluate_manual_symbols(self, report):
        report.return_value = ([], {"status": "ABSTAIN"})
        result = evaluate("unused.db", "2026-10-19")
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["ready"], 0)
        self.assertTrue(result["research_only"])

    @patch("tradepilot.v6_selected_history_refresh_cli.report")
    @patch("tradepilot.v6_selected_history_refresh_cli.yf.Ticker")
    def test_no_scanner_candidates_means_no_downloads(self, ticker, report):
        report.return_value = ([], {"status": "ABSTAIN"})
        result = refresh("unused.db", "2026-10-19")
        self.assertEqual(result["refreshed"], 0)
        ticker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
