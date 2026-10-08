"""Deterministic Scanner Service tests; no Yahoo requests or Streamlit required."""
import unittest
from unittest.mock import patch

from tradepilot.core.scanner_service import run_scan


def pre_screen(symbols, callback=None):
    passed = [{"ticker": s, "history": f"history-{s}"} for s in symbols]
    if callback:
        for i, symbol in enumerate(symbols, 1):
            callback(i, len(symbols), symbol)
    return {
        "total": len(symbols), "passed": passed, "excluded": [],
        "history_cache_hits": len(symbols), "seconds": 0.01,
    }


def score(symbol, **kwargs):
    return {
        "ticker": symbol,
        "opportunity": None if kwargs["etf_mode"] else
            {"score": {"AAA": 90, "BBB": 60}.get(symbol, 0)},
        "quality_gate": None if kwargs["etf_mode"] else {"passed": True},
        "score": 0.8,
        "passed": True,
    }


class ScannerServiceTests(unittest.TestCase):
    def setUp(self):
        self.pre = patch(
            "tradepilot.core.scanner_service.run_universe_pre_screen",
            side_effect=pre_screen,
        )
        self.scoring = patch(
            "tradepilot.core.scanner_service.score_stock",
            side_effect=score,
        )
        self.pre_mock = self.pre.start()
        self.score_mock = self.scoring.start()
        self.addCleanup(self.pre.stop)
        self.addCleanup(self.scoring.stop)

    def test_static_scan_preserves_history_and_opportunity_order(self):
        outcome = run_scan(tickers=["BBB", "AAA"])
        self.assertEqual([r["ticker"] for r in outcome.results], ["AAA", "BBB"])
        self.assertEqual(outcome.universe_result["total"], 2)
        self.assertEqual(self.score_mock.call_args_list[0].kwargs["price_history"], "history-BBB")
        self.assertIsNone(outcome.discovery_result)

    def test_dynamic_discovery_uses_returned_symbols(self):
        discovery = {
            "symbols": ["AAA", "BBB"], "discovered": 2,
            "mx": 0, "us": 2, "seconds": 0.1,
        }
        with patch(
            "tradepilot.core.scanner_service.discover_dynamic_universe",
            return_value=discovery,
        ) as mock:
            outcome = run_scan(dynamic_target=250)
        mock.assert_called_once_with(250)
        self.pre_mock.assert_called_once()
        self.assertEqual(self.pre_mock.call_args.args[0], ["AAA", "BBB"])
        self.assertEqual(outcome.discovery_result, discovery)

    def test_dynamic_empty_discovery_does_not_scan_fallback(self):
        with patch(
            "tradepilot.core.scanner_service.discover_dynamic_universe",
            return_value={"symbols": [], "discovered": 0},
        ):
            outcome = run_scan(dynamic_target=250)
        self.assertEqual(outcome.results, [])
        self.assertEqual(outcome.universe_result["total"], 0)
        self.pre_mock.assert_not_called()
        self.score_mock.assert_not_called()

    def test_etf_uses_legacy_no_prescreen_history(self):
        outcome = run_scan(tickers=["AAA"], etf_tickers=["SPY"])
        self.assertEqual(len(outcome.results), 2)
        self.assertEqual(self.score_mock.call_args_list[1].args[0], "SPY")
        self.assertTrue(self.score_mock.call_args_list[1].kwargs["etf_mode"])
        self.assertIsNone(self.score_mock.call_args_list[1].kwargs["price_history"])

    def test_progress_callbacks(self):
        pre_events, analysis_events = [], []
        run_scan(
            tickers=["AAA", "BBB"],
            pre_screen_progress=lambda *args: pre_events.append(args),
            analysis_progress=lambda *args: analysis_events.append(args),
        )
        self.assertEqual(pre_events[-1], (2, 2, "BBB"))
        self.assertEqual(analysis_events[-1], (2, 2, "BBB"))

    def test_runtime_rules_and_thresholds_are_forwarded(self):
        fund, tech = {"x": 1}, {"y": 2}
        run_scan(
            tickers=["AAA"], etf_tickers=["SPY"],
            fund_rules=fund, tech_rules=tech,
            stock_threshold=0.7, etf_threshold=0.9,
        )
        calls = self.score_mock.call_args_list
        self.assertIs(calls[0].kwargs["fund_rules"], fund)
        self.assertIs(calls[0].kwargs["tech_rules"], tech)
        self.assertEqual(calls[0].kwargs["threshold"], 0.7)
        self.assertEqual(calls[1].kwargs["threshold"], 0.9)

    def test_invalid_dynamic_request_rejected(self):
        with self.assertRaises(ValueError):
            run_scan(dynamic_target=0)
        with self.assertRaises(ValueError):
            run_scan(dynamic_target=250, tickers=["AAA"])

    def test_quality_passed_property(self):
        def mixed(symbol, **kwargs):
            result = score(symbol, **kwargs)
            result["quality_gate"] = {"passed": symbol == "AAA"}
            return result
        self.score_mock.side_effect = mixed
        outcome = run_scan(tickers=["AAA", "BBB"])
        self.assertEqual([r["ticker"] for r in outcome.quality_passed], ["AAA"])

    def test_no_streamlit_import_in_service_source(self):
        import inspect
        import tradepilot.core.scanner_service as module
        self.assertNotIn("import streamlit", inspect.getsource(module))


if __name__ == "__main__":
    unittest.main()
