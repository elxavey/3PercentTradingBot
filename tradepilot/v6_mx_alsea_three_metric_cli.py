"""TradePilot v6: ALSEA 2Q23 three-metric research bundle.

The official Q1 and Q2 reports give YTD consolidated CFO in thousands MXN.
This module derives quarterly CFO, joins existing IFRS comparison candidates,
and creates an auditable provisional score preview. NEVER exports VERIFIED rows.
"""
import argparse
import csv
import json
from pathlib import Path
from urllib.parse import urlparse

from tradepilot.v6_stop_target_cli import write_csv

Q1_URL = "https://www.alsea.net/uploads/es/documents/reports_quarterly/alsea_resultados_1T23a857.pdf?v=0000-00-00-12-00-00"
Q2_URL = "https://www.alsea.net/uploads/es/documents/reports_quarterly/alsea_resultados_2T23857f.pdf?v=2023-12-12-01-12-15"
# The URLs' query-string timestamps are NOT publication evidence.
CFO = {"2023": {"Q1": 1956750, "H1": 4438831},
       "2022": {"Q1": 1128544, "H1": 4498508}}
WEIGHTS = {"revenue": 35, "net_income": 35, "operating_cash_flow": 30}
COLUMNS = ("symbol","metric","basis","period_latest","period_previous",
           "latest_value","previous_value","change_pct","currency","scale",
           "source_url_latest","source_url_previous","source_page",
           "publication_status","verification_status","note")


def direction(pct):
    if pct > 5:
        return 100
    if pct < -5:
        return 0
    return 50


def build(comparisons):
    rows, warnings = [], []
    for basis in ("PRE_IFRS16", "POST_IFRS16_REEXPRESSED"):
        selected = {r["metric"]:r for r in comparisons
                    if r["basis"]==basis and r["symbol"]=="ALSEA.MX"
                    and r["verification_status"]=="PENDING_REVIEW"}
        for metric in ("revenue","net_income"):
            if metric not in selected:
                warnings.append(f"{basis}: missing comparable {metric}")
                continue
            item=selected[metric]
            rows.append(dict(symbol="ALSEA.MX",metric=metric,basis=basis,
                period_latest=item["period_latest"],period_previous=item["period_previous"],
                latest_value=item["latest_value"],previous_value=item["previous_value"],
                change_pct=item["calculated_change_pct"],currency=item["currency"],
                scale=item["scale"],source_url_latest=item["source_url"],
                source_url_previous=item["source_url"],source_page=item["source_page"],
                publication_status="REPORT_DATE_IN_CATALOG_NEEDS_AUDIT",
                verification_status="PENDING_REVIEW",
                note="Accounting basis and unit must be independently confirmed in issuer PDF"))
        latest=CFO["2023"]["H1"]-CFO["2023"]["Q1"]
        previous=CFO["2022"]["H1"]-CFO["2022"]["Q1"]
        rows.append(dict(symbol="ALSEA.MX",metric="operating_cash_flow",basis=basis,
            period_latest="2023-04-01/2023-06-30",
            period_previous="2022-04-01/2022-06-30",
            latest_value=latest,previous_value=previous,
            change_pct=round((latest-previous)/abs(previous)*100,3),
            currency="MXN",scale="1000",source_url_latest=Q2_URL,
            source_url_previous=Q1_URL,source_page="Q2 p.22; Q1 CFO statement",
            publication_status="ORIGINAL_PUBLICATION_DATES_UNVERIFIED",
            verification_status="PENDING_REVIEW",
            note="Quarter CFO = 6M minus 3M for each year; figures in thousands MXN. IFRS-basis compatibility with income metrics not established. Q1/Q2 URLs may have later upload metadata."))
    preview=[]
    for basis in ("PRE_IFRS16","POST_IFRS16_REEXPRESSED"):
        group=[r for r in rows if r["basis"]==basis]
        unique={r["metric"]:r for r in group}
        complete=set(unique)==set(WEIGHTS)
        points=(sum(WEIGHTS[k]*direction(float(unique[k]["change_pct"]))/100 for k in WEIGHTS)
                if complete else None)
        preview.append({"symbol":"ALSEA.MX","basis":basis,
                        "metrics_present":len(unique),"provisional_score":points if complete else "",
                        "status":"ILLUSTRATIVE_ONLY_NOT_PIT_VERIFIED" if complete else "INCOMPLETE",
                        "production_score":"","trade_decision":"",
                        "note":"Never feed this preview to financial quality or stop-target evaluation"})
    return rows,preview,warnings


def main(argv=None):
    parser=argparse.ArgumentParser(description="ALSEA CFO derivation and three-metric research preview")
    parser.add_argument("--comparisons",default=".cache/v6_mx_alsea_comparison_candidates.csv")
    parser.add_argument("--prefix",default=".cache/v6_mx_alsea_three_metric")
    args=parser.parse_args(argv)
    with Path(args.comparisons).open(encoding="utf-8-sig",newline="") as stream:
        comparisons=list(csv.DictReader(stream))
    rows,preview,warnings=build(comparisons)
    write_csv(args.prefix+"_observations_pending.csv",rows,COLUMNS)
    write_csv(args.prefix+"_preview.csv",preview,
              ("symbol","basis","metrics_present","provisional_score","status",
               "production_score","trade_decision","note"))
    path=Path(args.prefix+"_audit.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({
        "official_cfo_sources":[Q1_URL,Q2_URL],
        "cfo_ytd_thousands_mxn":CFO,
        "derived_cfo_quarter_thousands_mxn":{
            year:CFO[year]["H1"]-CFO[year]["Q1"] for year in CFO},
        "source_date_verified":False,"verified_observations":0,
        "production_scores_changed":False,"warnings":warnings,
        "blocking_issues":["Verify historical publication dates from contemporaneous evidence",
                           "Verify Q1 and Q2 CFO values, page, consolidation and reporting basis",
                           "Resolve accounting-basis compatibility for cash flow versus earnings",
                           "Review financial row unit and IFRS headers"]},
        indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"ALSEA: {len(rows)} provisional observations; CFO derived; scores unchanged")
    for p in preview:
        print(f"  {p['basis']}: illustrative={p['provisional_score'] or 'INCOMPLETE'}; not eligible for trading")


if __name__=="__main__":
    main()
