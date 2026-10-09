"""Phase 4.9 offline diagnostic tests."""
import unittest
from tradepilot.entry_diagnostics_cli import aggregate, analyze


def case(stop, holding, trades, wins, mean, exits):
    return {"stop_pct": stop, "holding_sessions": holding,
            "status": "RESEARCH_RESULT", "validation": "VALIDATED",
            "metrics": {"closed_trades": trades, "wins": wins,
                        "win_rate_pct": 100 * wins / trades if trades else None,
                        "average_net_return_pct": mean,
                        "profit_factor": None},
            "exit_reasons": exits}


class EntryDiagnosticsTests(unittest.TestCase):
    def test_weighted_aggregation(self):
        result = aggregate([case(4, 10, 1, 1, 2.0, {"TARGET": 1}),
                            case(4, 10, 3, 0, -2.0, {"STOP": 3})])
        self.assertEqual(result["closed_trades"], 4)
        self.assertEqual(result["wins"], 1)
        self.assertEqual(result["mean_net_return_pct"], -1.0)
        self.assertEqual(result["exit_reason_pct"]["STOP"], 75.0)

    def test_market_separation_and_ranking_gate(self):
        data = {"state": "HOLDING_SENSITIVITY_RESEARCH", "results": [
            {"symbol": "TEST.MX", "market": "MX",
             "scenarios": [case(4, 10, 2, 1, 1.0, {"TIME": 2})]},
            {"symbol": "TEST", "market": "US",
             "scenarios": [case(4, 10, 10, 2, -1.0, {"STOP": 8, "TARGET": 2})]},
        ]}
        result = analyze(data, min_trades=10)
        row = result["scenarios"][0]
        self.assertEqual(row["by_market"]["MX"]["closed_trades"], 2)
        self.assertEqual(row["by_market"]["US"]["closed_trades"], 10)
        self.assertEqual(row["ranked_best"][0]["symbol"], "TEST")
        self.assertEqual(row["insufficient_sample_symbols"], ["TEST.MX"])
        self.assertFalse(result["actionable"])

    def test_reject_summary_only_input(self):
        with self.assertRaises(ValueError):
            analyze({"state": "HOLDING_SENSITIVITY_RESEARCH", "summaries": []})


if __name__ == "__main__":
    unittest.main()
