import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from tradepilot.v6_actual_scanner_report_cli import report


class ActualScannerReportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Path(self.temp.name)/"tradepilot.db"
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("CREATE TABLE scan_runs (id INTEGER PRIMARY KEY, status TEXT, finished_at_utc TEXT)")
            conn.execute("CREATE TABLE scan_candidates (scan_run_id INTEGER, symbol TEXT, exchange_code TEXT, currency TEXT, quality_pass INTEGER, opportunity_score REAL, observed_at_utc TEXT, price_source TEXT, price REAL)")
            conn.execute("INSERT INTO scan_runs VALUES (1,'SUCCEEDED','2026-10-19T22:00:00Z')")
            conn.executemany("INSERT INTO scan_candidates VALUES (?,?,?,?,?,?,?,?,?)",[
                (1,"AUTO1","US","USD",1,81,"2026-10-19T21:00:00Z","provider",100),
                (1,"AUTO2","US","USD",1,90,"2026-10-19T21:00:00Z","provider",50),
                (1,"REJECT","US","USD",0,99,"2026-10-19T21:00:00Z","provider",50)])
            conn.commit()

    def tearDown(self):
        self.temp.cleanup()

    def test_real_ranking_and_no_fake_setup(self):
        rows,summary=report(self.db,"2026-10-19",limit=2)
        self.assertEqual([r["symbol"] for r in rows],["AUTO2","AUTO1"])
        self.assertEqual(rows[0]["setup_status"],"UNVERIFIED")
        self.assertEqual(rows[0]["entry"],"")
        self.assertEqual(summary["scanner_candidates"],3)

    def test_stale_abstains(self):
        rows,summary=report(self.db,"2026-10-20")
        self.assertEqual(rows,[])
        self.assertEqual(summary["status"],"ABSTAIN")

    def test_preclose_scanner_run_abstains(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("UPDATE scan_runs SET finished_at_utc=? WHERE id=1",("2026-10-19T15:34:38Z",))
            conn.commit()
        rows,summary=report(self.db,"2026-10-19")
        self.assertEqual(rows,[])
        self.assertEqual(summary["status"],"ABSTAIN")
        self.assertEqual(summary["excluded"]["PRE_CLOSE_OR_NON_SESSION_RUN"],2)

    def test_invalid_limit_rejected(self):
        with self.assertRaisesRegex(ValueError,"limit"):
            report(self.db,"2026-10-19",limit=0)

    def test_run_id_filter(self):
        rows,summary=report(self.db,"2026-10-19",run_id=1)
        self.assertEqual(summary["run_id"],1)
        self.assertEqual(len(rows),2)

if __name__=="__main__":
    unittest.main()
