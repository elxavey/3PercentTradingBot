"""Research-only retrospective filter comparison with explicit missing-score policies.

Never uses outcomes as scoring features. A retrospective case-control sample is
not a trading performance estimate. No optimizer, execution or production filter.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from tradepilot.v6_stop_target_cli import write_csv

COLUMNS=("threshold","missing_policy","total","scored","unscored",
         "retained","excluded","retained_stop","retained_target",
         "excluded_stop","excluded_target","baseline_net_sum",
         "retained_net_sum","excluded_net_sum","retained_mean_net_pct",
         "baseline_mean_net_pct","eligible_for_inference")


def evaluate(cases,quality,thresholds=(35,50,65),policies=("RETAIN","ABSTAIN")):
    by_id={}
    for q in quality:
        if q["case_id"] in by_id:
            raise ValueError("Duplicate quality case")
        by_id[q["case_id"]]=q
    if set(by_id)!={c["case_id"] for c in cases}:
        raise ValueError("Case/quality IDs differ")
    records=[]
    for case in cases:
        q=by_id[case["case_id"]]
        if any(q[k]!=case[k] for k in ("symbol","market","signal_date")):
            raise ValueError(f"Case identity mismatch: {case['case_id']}")
        if case["fixed_outcome"] not in ("STOP","TARGET"):
            raise ValueError("Unknown outcome")
        complete=q["quality_status"]=="EXPERIMENTAL_COMPLETE"
        if complete and str(q.get("coverage_pct")) not in ("100","100.0"):
            raise ValueError("Complete score requires 100% coverage")
        if not complete and str(q.get("quality_score","")).strip():
            raise ValueError("Incomplete case has score")
        score=float(q["quality_score"]) if complete else None
        if score is not None and not 0<=score<=100:
            raise ValueError("Score outside 0..100")
        try:
            net=float(case["fixed_net_pct"])
        except (ValueError,TypeError) as exc:
            raise ValueError("Missing fixed_net_pct; cannot compare returns") from exc
        records.append((case,q,score,net))
    result=[]
    for threshold in thresholds:
        for policy in policies:
            if policy not in ("RETAIN","ABSTAIN"):
                raise ValueError("Unknown missing-score policy")
            kept=[r for r in records if r[2] is not None and r[2]>=threshold
                  or (r[2] is None and policy=="RETAIN")]
            excluded=[r for r in records if r not in kept]
            count=lambda rows,outcome:sum(r[0]["fixed_outcome"]==outcome for r in rows)
            result.append(dict(threshold=threshold,missing_policy=policy,
                total=len(records),scored=sum(r[2] is not None for r in records),
                unscored=sum(r[2] is None for r in records),
                retained=len(kept),excluded=len(excluded),
                retained_stop=count(kept,"STOP"),retained_target=count(kept,"TARGET"),
                excluded_stop=count(excluded,"STOP"),excluded_target=count(excluded,"TARGET"),
                baseline_net_sum=round(sum(r[3] for r in records),4),
                retained_net_sum=round(sum(r[3] for r in kept),4),
                excluded_net_sum=round(sum(r[3] for r in excluded),4),
                retained_mean_net_pct=round(sum(r[3] for r in kept)/len(kept),4) if kept else "",
                baseline_mean_net_pct=round(sum(r[3] for r in records)/len(records),4) if records else "",
                eligible_for_inference="NO_CASE_CONTROL_SAMPLE"))
    summary={"cases":len(records),"outcomes":dict(Counter(c["fixed_outcome"] for c in cases)),
             "scored":sum(r[2] is not None for r in records),
             "thresholds":list(thresholds),"missing_policies":list(policies),
             "baseline_scope":"Retrospective selected cases, not a portfolio return",
             "limitations":["Case-control selection conditions on future outcomes; no predictive performance claims",
                            "Sum of per-trade returns is not portfolio P&L",
                            "No confidence intervals or significance claims with this biased pilot",
                            "Weights and thresholds must be frozen before out-of-sample validation",
                            "ABSTAIN is a missing-data policy, not a negative financial assessment",
                            "No live trading changes"]}
    return result,summary


def read(path):
    with Path(path).open(newline="",encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main(argv=None):
    parser=argparse.ArgumentParser(description="Retrospective financial filter sensitivity research")
    parser.add_argument("--cases",default=".cache/v6_pilot_cases.csv")
    parser.add_argument("--quality",default=".cache/v6_financial_engine_quality.csv")
    parser.add_argument("--prefix",default=".cache/v6_financial_filter")
    args=parser.parse_args(argv)
    rows,summary=evaluate(read(args.cases),read(args.quality))
    write_csv(args.prefix+"_comparison.csv",rows,COLUMNS)
    p=Path(args.prefix+"_summary.json")
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"Filter sensitivity: {len(rows)} scenarios; retrospective only; no predictive validation")


if __name__=="__main__":
    main()
