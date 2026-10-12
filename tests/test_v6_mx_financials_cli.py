import unittest
from tradepilot.v6_mx_financials_cli import validated_observations, mx_trends


def observation(metric, start, end, published, value):
    return {"symbol": "ALSEA.MX", "metric": metric, "period_start": start,
            "period_end": end, "published_at": published, "value": str(value),
            "currency": "MXN", "scale": "1000000",
            "source_url": "https://www.alsea.net/inversionistas/2023.html",
            "source_page": "4", "verification_status": "VERIFIED"}


class MexicoTests(unittest.TestCase):
    def setUp(self):
        self.case = {"case_id": "V6-001", "symbol": "ALSEA.MX", "market": "MX",
                     "signal_date": "2023-08-15"}
        self.rows = [
            observation("revenue", "2022-04-01", "2022-06-30", "2022-07-20", 100),
            observation("revenue", "2023-04-01", "2023-06-30", "2023-07-21", 120),
        ]

    def test_yoy_from_verified_quarters(self):
        facts, errors = validated_observations(self.rows)
        result = mx_trends([self.case], facts)
        self.assertFalse(errors)
        self.assertEqual(result[0]["change_pct"], 20)
        self.assertEqual(result[0]["latest_value"], 120000000)
        self.assertEqual(result[0]["status"], "CANDIDATE_YOY")

    def test_later_publication_is_excluded(self):
        self.rows[1]["published_at"] = "2023-08-15"
        facts, _ = validated_observations(self.rows)
        self.assertEqual(mx_trends([self.case], facts)[0]["status"], "MISSING_YOY_COMPARISON")

    def test_unverified_rows_not_used(self):
        self.rows[1]["verification_status"] = "PENDING"
        facts, _ = validated_observations(self.rows)
        self.assertEqual(len(facts[("ALSEA.MX", "revenue")]), 1)

    def test_missing_source_page_rejected(self):
        self.rows[1]["source_page"] = ""
        facts, errors = validated_observations(self.rows)
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(facts[("ALSEA.MX", "revenue")]), 1)

    def test_currency_mismatch_no_comparison(self):
        self.rows[1]["currency"] = "USD"
        facts, _ = validated_observations(self.rows)
        self.assertEqual(mx_trends([self.case], facts)[0]["status"], "MISSING_YOY_COMPARISON")


if __name__ == "__main__":
    unittest.main()
