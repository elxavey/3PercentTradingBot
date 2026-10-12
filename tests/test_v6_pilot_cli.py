"""Tests for the v6 historical pilot selector."""
import json
import tempfile
import unittest
from pathlib import Path

from tradepilot.v6_pilot_cli import select_cases, write_pilot


def record(symbol, market, strategy, outcome, date):
    return {
        "symbol": symbol, "market": market, "strategy": strategy,
        "signal_date": date, "entry_date": date,
        "exit_comparison": {
            "FIXED_3PCT": {"outcome": outcome, "sessions_held": 3, "net_pct": 3.0 if outcome == "TARGET" else -3.58},
            "STRUCTURAL": {"outcome": "TARGET"},
            "NO_STOP": {"outcome": "TARGET", "sessions_held": 7,
                        "max_drawdown_before_exit_pct_excluding_entry_bar": 2.0},
        },
    }


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.payload = {"signals": [
            record(f"{market}{strategy}{outcome}", market, strategy, outcome, "2024-01-10")
            for market in ("MX", "US")
            for strategy in ("BREAKOUT", "REBOUND")
            for outcome in ("STOP", "TARGET")
        ]}

    def test_deterministic_balanced_selection(self):
        a = select_cases(self.payload, per_outcome=4)
        b = select_cases(self.payload, per_outcome=4)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 8)
        self.assertEqual({r["market"] for r in a}, {"MX", "US"})
        self.assertEqual({r["strategy"] for r in a}, {"BREAKOUT", "REBOUND"})
        self.assertEqual(sum(r["fixed_outcome"] == "STOP" for r in a), 4)

    def test_invalid_and_untriggered_entries_excluded(self):
        self.payload["signals"].append({
            "symbol": "BAD", "market": "MX", "strategy": "BREAKOUT",
            "signal_date": "2024-01-01", "entry_date": None,
            "exit_comparison": {"FIXED_3PCT": {"outcome": "ENTRY_NOT_TRIGGERED"}},
        })
        self.assertEqual(len(select_cases(self.payload, 4)), 8)

    def test_files_are_written_with_unresearched_status(self):
        with tempfile.TemporaryDirectory() as temp:
            rows, csv_path, json_path = write_pilot(self.payload, temp, 4)
            self.assertTrue(csv_path.exists())
            self.assertEqual(len(rows), 8)
            evidence = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(len(evidence["cases"]), 8)
            self.assertTrue(all(c["review_status"] == "NOT_RESEARCHED" for c in evidence["cases"]))

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            select_cases({"signals": []}, 0)
        with self.assertRaises(ValueError):
            select_cases({})


if __name__ == "__main__":
    unittest.main()
