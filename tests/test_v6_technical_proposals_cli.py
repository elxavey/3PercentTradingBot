import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tradepilot.v6_technical_proposals_cli import proposals


class TechnicalProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "scanner.db"
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("CREATE TABLE scan_runs (id TEXT, status TEXT, finished_at_utc TEXT)")
            conn.execute("CREATE TABLE scan_candidates (scan_run_id TEXT, symbol TEXT, exchange_code TEXT, currency TEXT, quality_pass INTEGER, opportunity_score REAL, observed_at_utc TEXT, price_source TEXT, price REAL)")
            conn.execute("CREATE TABLE market_data_observations (symbol TEXT, interval TEXT, bar_end_utc TEXT, source TEXT, fetched_at_utc TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)")
            conn.execute("INSERT INTO scan_runs VALUES ('run1','SUCCEEDED','2026-10-19T22:00:00Z')")
            conn.execute("INSERT INTO scan_candidates VALUES ('run1','AUTO','US','USD',1,80,'2026-10-19T21:00:00Z','provider',120)")
            conn.commit()

    def tearDown(self):
        self.temp.cleanup()

    def _history(self):
        with closing(sqlite3.connect(self.db)) as conn:
            # Weekdays only, 21 daily bars ending on Monday Oct 19, 2026.
            day = datetime(2026,9,21,21,tzinfo=timezone.utc)
            count = 0
            while day.date() <= datetime(2026,10,19,tzinfo=timezone.utc).date():
                if day.weekday() < 5:
                    close = 120 if day.date().isoformat()=="2026-10-19" else 100
                    conn.execute("INSERT INTO market_data_observations VALUES (?,?,?,?,?,?,?,?,?,?)",
                        ("AUTO","1d",day.isoformat(),"provider",(day+timedelta(minutes=5)).isoformat(),
                         close-1,close+1,close-2,close,1000))
                    count += 1
                day += timedelta(days=1)
            conn.commit()
        self.assertEqual(count,21)

    def test_no_history_never_ready(self):
        rows,summary=proposals(self.db,"2026-10-19")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["classification"],"WATCHING")
        self.assertEqual(rows[0]["reason"],"NO_DATED_DAILY_BAR_FOR_SESSION")
        self.assertEqual(summary["ready"],0)

    def test_prototype_breakout_is_only_watching(self):
        self._history()
        rows,summary=proposals(self.db,"2026-10-19")
        self.assertEqual(rows[0]["pattern"],"BREAKOUT")
        self.assertEqual(rows[0]["classification"],"WATCHING")
        self.assertGreater(rows[0]["target"],rows[0]["entry"])
        self.assertLess(rows[0]["stop"],rows[0]["entry"])
        self.assertAlmostEqual(rows[0]["estimated_net_pct"],3,places=3)
        self.assertEqual(summary["ready"],0)

    def test_preclose_abstains_without_symbols(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("UPDATE scan_runs SET finished_at_utc='2026-10-19T15:34:38Z'")
            conn.commit()
        rows,summary=proposals(self.db,"2026-10-19")
        self.assertEqual(rows,[])
        self.assertEqual(summary["candidates_evaluated"],0)

    def test_invalid_fee_rejected(self):
        with self.assertRaisesRegex(ValueError,"fee"):
            proposals(self.db,"2026-10-19",fee_rate=1)


if __name__=="__main__":
    unittest.main()
