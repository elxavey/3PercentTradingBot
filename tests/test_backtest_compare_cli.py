import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from tradepilot.backtest_compare_cli import compare_symbols, normalize_symbols, main
from tradepilot.historical_simulator import SimulationPolicy

NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)
POLICY = SimulationPolicy(fee_rate_per_side=.0025, slippage_rate_per_side=.001)


def report(symbol, trades, avg, *, validation="VALIDATED"):
    return {"state": "RESEARCH_RESULT", "validation": {"state": validation},
            "backtest": {"historical_sessions": 500,
                         "confirmed_signal_sessions": trades,
                         "metrics": {"closed_trades": trades, "wins": trades,
                                     "losses": 0, "breakeven": 0,
                                     "win_rate_pct": 100., "average_net_return_pct": avg,
                                     "average_win_pct": avg, "average_loss_pct": None,
                                     "average_holding_sessions": 2.,
                                     "compounded_net_return_pct": avg,
                                     "max_closed_trade_drawdown_pct": 0.,
                                     "profit_factor": None}}}


class ComparisonTests(unittest.TestCase):
    def test_normalize_and_deduplicate(self):
        self.assertEqual(normalize_symbols([" alsea.mx ", "ALSEA.MX", "AAPL"]), ["ALSEA.MX", "AAPL"])

    def test_empty_symbols_rejected(self):
        with self.assertRaises(ValueError):
            normalize_symbols([])

    def test_research_only_and_sample_ranking(self):
        def runner(history, *, symbol, **kwargs):
            return report(symbol, 12 if symbol == "AAPL" else 5, 1.1)
        with patch("tradepilot.backtest_compare_cli.exploratory_backtest", side_effect=runner):
            result = compare_symbols(["AAPL", "ALSEA.MX"], simulation_policy=POLICY,
                                     as_of_utc=NOW, fetcher=lambda *a, **kw: object())
        self.assertEqual(result["symbols_validated"], 2)
        self.assertEqual([r["symbol"] for r in result["ranking"]], ["AAPL"])
        self.assertFalse(result["actionable"])
        self.assertEqual(result["results"][1]["market"], "MX")

    def test_ranking_average_net_return(self):
        def runner(history, *, symbol, **kwargs):
            return report(symbol, 12, 1.5 if symbol == "AAPL" else -.5)
        with patch("tradepilot.backtest_compare_cli.exploratory_backtest", side_effect=runner):
            result = compare_symbols(["MSFT", "AAPL"], simulation_policy=POLICY,
                                     as_of_utc=NOW, fetcher=lambda *a, **kw: object())
        self.assertEqual([r["symbol"] for r in result["ranking"]], ["AAPL", "MSFT"])

    def test_reject_and_error_are_visible(self):
        def runner(history, *, symbol, **kwargs):
            return {"state": "REJECT", "reasons": ["MISSING_EXCHANGE_SESSIONS"],
                    "validation": {"state": "REJECT"}} if symbol == "AAPL" else report(symbol, 10, 1.)
        def fetcher(symbol, **kwargs):
            if symbol == "MSFT":
                raise RuntimeError("provider unavailable")
            return object()
        with patch("tradepilot.backtest_compare_cli.exploratory_backtest", side_effect=runner):
            result = compare_symbols(["AAPL", "MSFT", "ALSEA.MX"],
                                     simulation_policy=POLICY, as_of_utc=NOW, fetcher=fetcher)
        self.assertEqual(result["symbols_rejected"], 1)
        self.assertEqual(result["symbols_errored"], 1)
        self.assertEqual(result["symbols_validated"], 1)

    def test_strict_uses_strict_runner(self):
        with patch("tradepilot.backtest_compare_cli.validated_backtest",
                   return_value=report("AAPL", 10, 1.)) as runner:
            result = compare_symbols(["AAPL"], simulation_policy=POLICY,
                                     as_of_utc=NOW, strict=True, fetcher=lambda *a, **kw: object())
        self.assertEqual(result["mode"], "STRICT")
        runner.assert_called_once()

    def test_no_zero_cost_backtest(self):
        with self.assertRaises(ValueError):
            compare_symbols(["AAPL"], simulation_policy=SimulationPolicy(),
                            as_of_utc=NOW, fetcher=lambda *a, **kw: object())


if __name__ == "__main__":
    unittest.main()
