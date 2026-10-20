import csv
import gc
import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from tradepilot.v6_scanner_bridge_cli import schema,source_rows,normalize
from tradepilot.v6_daily_close_simulation_cli import simulate


class ScannerBridgeTests(unittest.TestCase):
    def test_csv_real_rows_no_symbol_injection(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"scanner.csv"
            row=dict(symbol="EXAMPLE.MX",market="MX",strategy="BREAKOUT",
                signal_status="CONFIRMED",reference_date="2026-10-19",
                close="100",currency="MXN",opportunity_score="81",
                entry="101",target="105",stop="98")
            with path.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=row)
                w.writeheader()
                w.writerow(row)
            source=source_rows(csv_path=str(path))
            _,selected,_=simulate(normalize(source),"2026-10-19")
            self.assertEqual([r["symbol"] for r in selected],["EXAMPLE.MX"])

    def test_sqlite_read_only_and_explicit_mapping(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"scanner.sqlite"
            with closing(sqlite3.connect(db)) as conn:
                conn.execute("CREATE TABLE signals (ticker TEXT, market TEXT, strategy TEXT, signal_status TEXT, reference_date TEXT, close REAL, currency TEXT, opportunity_score REAL, entry REAL, target REAL, stop REAL)")
                conn.execute("INSERT INTO signals VALUES ('XYZ','US','PULLBACK','CONFIRMED','2026-10-19',100,'USD',85,101,105,98)")
                conn.commit()
            self.assertIn("signals",schema(db))
            mapping={k:k for k in ("symbol","market","strategy","signal_status","reference_date",
                                  "close","currency","opportunity_score","entry","target","stop")}
            mapping["symbol"]="ticker"
            rows=normalize(source_rows(db_path=str(db),table="signals"),mapping)
            _,selected,_=simulate(rows,"2026-10-19")
            self.assertEqual(selected[0]["symbol"],"XYZ")
            with closing(sqlite3.connect(db)) as conn:
                with closing(conn.execute("SELECT COUNT(*) FROM signals")) as cursor:
                    self.assertEqual(cursor.fetchone()[0],1)
            # Windows can retain SQLite file handles until pending cursors are finalized.
            gc.collect()

    def test_unknown_table_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"scanner.sqlite"
            with closing(sqlite3.connect(db)):
                pass
            with self.assertRaisesRegex(ValueError,"Unknown SQLite table"):
                source_rows(db_path=str(db),table="does_not_exist")

    def test_missing_mapped_column_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"lacks required mapped values"):
            normalize([{"symbol":"XYZ"}])

    def test_mapping_requires_complete_schema(self):
        with self.assertRaisesRegex(ValueError,"exactly"):
            normalize([{"symbol":"XYZ"}],{"symbol":"symbol"})

if __name__=="__main__":
    unittest.main()
