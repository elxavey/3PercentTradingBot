"""Post-close pipeline safety and output tests."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tradepilot.v6_postclose_pipeline_cli import run, save


class PostclosePipelineTests(unittest.TestCase):
    @patch("tradepilot.v6_postclose_pipeline_cli.refresh")
    @patch("tradepilot.v6_postclose_pipeline_cli.evaluate")
    @patch("tradepilot.v6_postclose_pipeline_cli.report")
    def test_abstain_never_refreshes_or_evaluates(self, report, evaluate, refresh):
        report.return_value = ([], {"status": "ABSTAIN"})
        result = run("unused.db", "2026-10-19", download=True)
        self.assertEqual(result["status"], "ABSTAIN")
        self.assertEqual(result["orders_sent"], 0)
        evaluate.assert_not_called()
        refresh.assert_not_called()

    @patch("tradepilot.v6_postclose_pipeline_cli.refresh")
    @patch("tradepilot.v6_postclose_pipeline_cli.evaluate")
    @patch("tradepilot.v6_postclose_pipeline_cli.report")
    def test_selected_symbols_only(self, report, evaluate, refresh):
        report.return_value = ([{"symbol": "SCANNER_SELECTED"}], {"status": "POST_CLOSE_SCAN_UNVERIFIED_BAR"})
        evaluate.return_value = {"candidates": [{"symbol": "SCANNER_SELECTED", "state": "WATCHING", "actionable": False}]}
        refresh.return_value = {"refreshed": 1, "results": []}
        result = run("unused.db", "2026-10-19", download=True)
        self.assertEqual(result["selected"], 1)
        self.assertEqual(result["refreshed"], 1)
        self.assertEqual(result["orders_sent"], 0)
        self.assertFalse(result["candidates"][0]["actionable"])

    def test_report_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_file, csv_file = save({"status": "ABSTAIN", "candidates": []}, str(Path(tmp) / "report"))
            self.assertEqual(json.loads(Path(json_file).read_text())["status"], "ABSTAIN")
            with open(csv_file, encoding="utf-8-sig", newline="") as handle:
                self.assertEqual(list(csv.DictReader(handle)), [])


if __name__ == "__main__":
    unittest.main()
