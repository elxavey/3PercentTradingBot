"""Point-in-time evidence validation tests."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from tradepilot.v6_evidence_cli import consolidate, validate_evidence


def fact(published="2024-01-09T15:00:00-05:00", availability=True):
    return {
        "category": "EARNINGS", "assessment": "RISK",
        "headline": "Company reports lower guidance",
        "source_url": "https://example.org/investors/report",
        "published_at": published,
        "available_by_signal_close": availability,
        "notes": "Contemporaneous report",
    }


class EvidenceTests(unittest.TestCase):
    def test_prior_day_fact_is_usable(self):
        self.assertEqual(validate_evidence(fact(), "2024-01-10"), (True, "OK"))

    def test_future_and_same_day_without_cutoff_are_excluded(self):
        self.assertFalse(validate_evidence(fact("2024-01-11T09:00:00Z"), "2024-01-10")[0])
        self.assertFalse(validate_evidence(fact("2024-01-10T10:00:00Z"), "2024-01-10")[0])

    def test_explicit_cutoff_and_timezone(self):
        cutoff = "2024-01-10T16:00:00-05:00"
        self.assertTrue(validate_evidence(fact("2024-01-10T15:00:00-05:00"), "2024-01-10", cutoff)[0])
        self.assertFalse(validate_evidence(fact("2024-01-10T17:00:00-05:00"), "2024-01-10", cutoff)[0])
        self.assertFalse(validate_evidence(fact("2024-01-09T15:00:00"), "2024-01-10")[0])

    def test_missing_source_or_unverified_availability(self):
        self.assertFalse(validate_evidence(fact(availability=False), "2024-01-10")[0])
        item = fact()
        item["source_url"] = ""
        self.assertFalse(validate_evidence(item, "2024-01-10")[0])

    def test_consolidation_and_identity_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            cases = Path(folder) / "cases.csv"
            evidence = Path(folder) / "evidence.json"
            with cases.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["case_id", "symbol", "market",
                    "strategy", "signal_date", "fixed_outcome"])
                writer.writeheader()
                writer.writerow({"case_id": "V6-001", "symbol": "ABC", "market": "US",
                    "strategy": "BREAKOUT", "signal_date": "2024-01-10", "fixed_outcome": "STOP"})
            document = {"schema_version": 1, "cases": [{"case_id": "V6-001",
                "symbol": "ABC", "signal_date": "2024-01-10", "review_status": "IN_PROGRESS",
                "evidence": [fact(), fact("2024-01-12T12:00:00Z")]}]}
            evidence.write_text(json.dumps(document), encoding="utf-8")
            rows = consolidate(cases, evidence)
            self.assertEqual(rows[0]["usable_evidence"], 1)
            self.assertEqual(rows[0]["excluded_evidence"], 1)
            document["cases"][0]["symbol"] = "WRONG"
            evidence.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(ValueError):
                consolidate(cases, evidence)


if __name__ == "__main__":
    unittest.main()
