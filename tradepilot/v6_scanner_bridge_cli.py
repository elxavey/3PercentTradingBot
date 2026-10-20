"""Read-only bridge from TradePilot scanner exports / SQLite snapshots to v6 dry run.

Does not discover symbols or create trades. All source field mappings are explicit
and inspectable. SQLite reads use a read-only URI, never mutate the scanner DB.
"""
import argparse
import csv
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from tradepilot.v6_daily_close_simulation_cli import REQUIRED, read as read_csv, simulate, COLUMNS
from tradepilot.v6_stop_target_cli import write_csv

DEFAULT_MAP={k:k for k in REQUIRED}
SCANNER_COLUMNS=tuple(REQUIRED)


def schema(db):
    with closing(sqlite3.connect(Path(db).resolve().as_uri()+"?mode=ro",uri=True)) as conn:
        tables=conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        return {name:[row[1] for row in conn.execute('PRAGMA table_info("'+name.replace('"','""')+'")')] for (name,) in tables}


def source_rows(csv_path=None,db_path=None,table=None):
    if bool(csv_path)==bool(db_path):
        raise ValueError("Specify exactly one source: --csv or --db")
    if csv_path:
        return read_csv(csv_path)
    if not table:
        raise ValueError("SQLite source requires --table; use --inspect to list tables")
    tables=schema(db_path)
    if table not in tables:
        raise ValueError(f"Unknown SQLite table: {table}. Available: {', '.join(tables)}")
    with sqlite3.connect(Path(db_path).resolve().as_uri()+"?mode=ro",uri=True) as conn:
        conn.row_factory=sqlite3.Row
        quoted=table.replace('"','""')
        return [dict(row) for row in conn.execute(f'SELECT * FROM "{quoted}"')]


def normalize(rows,mapping=None):
    mapping=mapping or DEFAULT_MAP
    if set(mapping)!=set(REQUIRED):
        raise ValueError(f"Mapping must provide exactly these target fields: {', '.join(REQUIRED)}")
    result=[]
    for idx,row in enumerate(rows,2):
        normalized={target:row.get(source,"") for target,source in mapping.items()}
        missing=[k for k,v in normalized.items() if v is None or str(v).strip()==""]
        if missing:
            raise ValueError(f"Scanner row {idx} lacks required mapped values: {', '.join(missing)}")
        result.append(normalized)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description="Read-only scanner snapshot -> daily-close dry run")
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--csv",help="Actual scanner candidate CSV")
    group.add_argument("--db",help="Existing scanner SQLite file, opened read-only")
    parser.add_argument("--table",help="Explicit SQLite table")
    parser.add_argument("--inspect",action="store_true",help="List SQLite table columns without running a simulation")
    parser.add_argument("--mapping",help="Optional JSON dictionary target_field -> source_field")
    parser.add_argument("--as-of",help="YYYY-MM-DD exchange close date")
    parser.add_argument("--top",type=int,default=3)
    parser.add_argument("--prefix",default=".cache/v6_daily_close")
    args=parser.parse_args(argv)
    if args.inspect:
        if not args.db:
            parser.error("--inspect requires --db")
        print(json.dumps(schema(args.db),indent=2,ensure_ascii=False))
        return
    if not args.as_of:
        parser.error("--as-of is required unless --inspect")
    mapping=json.loads(Path(args.mapping).read_text(encoding="utf-8")) if args.mapping else DEFAULT_MAP
    rows=normalize(source_rows(args.csv,args.db,args.table),mapping)
    evaluated,selected,summary=simulate(rows,args.as_of,top_per_market=args.top)
    summary["input_source"]="sqlite_readonly" if args.db else "scanner_csv"
    summary["source_rows"]=len(rows)
    summary["mapping"]="explicit_json" if args.mapping else "identity"
    write_csv(args.prefix+"_evaluated.csv",evaluated,COLUMNS)
    write_csv(args.prefix+"_selected.csv",selected,COLUMNS)
    output=Path(args.prefix+"_summary.json")
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"Scanner bridge: {len(rows)} actual source rows; {len(selected)} ranked; {summary['status']}")
    for r in selected:
        print(f"{r['market']} #{r['rank']} {r['symbol']} {r['strategy']} score={r['opportunity_score']} entry={r['entry']} target={r['target']} stop={r['stop']}")
    if not selected:
        print("ABSTAIN: no valid same-date confirmed scanner setups")
    print("Read-only simulation. No synthetic tickers or orders.")


if __name__=="__main__":
    main()
