"""Market-neutral financial evidence staging.

Reads CSV source observations and generic YTD derivation rules. A source row is
scorable only when VERIFIED and its publication date is independently proven.
Research-only rows and derived cash flows remain visible but cannot be scored.
No issuer-specific code or automatic promotion of PDF candidates.
"""
import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path

from tradepilot.v6_mx_financials_cli import INPUT_COLUMNS
from tradepilot.v6_stop_target_cli import write_csv

EVIDENCE_COLUMNS = INPUT_COLUMNS + ("publication_evidence","accounting_basis","consolidation",
                                   "derivation","review_note")
YTD_COLUMNS = ("symbol","metric","fiscal_year","quarter","period_end","value",
               "currency","scale","source_url","source_page","published_at",
               "publication_evidence","accounting_basis","consolidation","verification_status")
AUDIT_COLUMNS = ("symbol","metric","period_end","status","reason")
VALID_DATE_PROOF = ("ISSUER_DATED_RELEASE","EXCHANGE_FILING_TIMESTAMP","SEC_ACCEPTED_TIMESTAMP")
VALID_BASES = ("IFRS","US_GAAP","PRE_IFRS16","POST_IFRS16","UNSPECIFIED")
VALID_CONSOLIDATION = ("CONSOLIDATED","STANDALONE","UNCONFIRMED")


def stage(direct, ytd):
    staged, audit = [], []
    for row in direct:
        staged.append({k:row.get(k,"") for k in EVIDENCE_COLUMNS})
    by_key={}
    for row in ytd:
        key=(row["symbol"].upper(),row["metric"],row["fiscal_year"],
             row["currency"],row["scale"],row["accounting_basis"],row["consolidation"])
        by_key.setdefault(key,{})
        quarter=int(row["quarter"])
        if quarter not in (1,2,3,4) or quarter in by_key[key]:
            raise ValueError(f"Duplicate or invalid YTD quarter for {key}: {quarter}")
        by_key[key][quarter]=row
    for key, periods in by_key.items():
        symbol,metric,year,currency,scale,basis,consolidation=key
        for quarter,row in sorted(periods.items()):
            prev=periods.get(quarter-1)
            if quarter>1 and prev is None:
                audit.append(dict(symbol=symbol,metric=metric,period_end=row["period_end"],
                                  status="MISSING_PRIOR_YTD",reason="Cannot derive quarter without prior YTD"))
                continue
            if quarter>1 and date.fromisoformat(prev["period_end"]) >= date.fromisoformat(row["period_end"]):
                raise ValueError(f"YTD period order invalid for {key}")
            value=float(row["value"])-(float(prev["value"]) if prev else 0)
            period_end=date.fromisoformat(row["period_end"])
            # Quarter start derived from end of preceding calendar quarter, not guessed from a report title.
            from datetime import timedelta
            period_start=(date(int(year),3*(quarter-1)+1,1)).isoformat()
            if period_end.month != 3*quarter or period_end.year != int(year):
                raise ValueError(f"YTD fiscal/calendar alignment ambiguous for {key}; provide direct quarter evidence")
            published=max(row["published_at"],prev["published_at"] if prev else row["published_at"])
            proven=(row["publication_evidence"] in VALID_DATE_PROOF
                    and (prev is None or prev["publication_evidence"] in VALID_DATE_PROOF))
            verified=(row["verification_status"]=="VERIFIED"
                      and (prev is None or prev["verification_status"]=="VERIFIED")
                      and proven and consolidation=="CONSOLIDATED"
                      and basis!="UNSPECIFIED")
            status="VERIFIED" if verified else "PENDING_REVIEW"
            staged.append(dict(symbol=symbol,metric=metric,period_start=period_start,
                period_end=row["period_end"],published_at=published,value=str(value),
                currency=currency,scale=scale,source_url=row["source_url"],
                source_page=row["source_page"],verification_status=status,
                publication_evidence=row["publication_evidence"],
                accounting_basis=basis,consolidation=consolidation,
                derivation=f"YTD_Q{quarter}"+(f"-YTD_Q{quarter-1}" if prev else ""),
                review_note="Derived from cumulative statements; inspect both source pages and original publication timestamps"))
            audit.append(dict(symbol=symbol,metric=metric,period_end=row["period_end"],
                              status=status,reason="YTD derived; proof and accounting basis checked" if verified else "Derived research lead; source/date/basis not fully proven"))
    # Direct observations require source and publication proof before eligibility.
    eligible=[]
    for row in staged:
        status=row.get("verification_status","").upper()
        proof=row.get("publication_evidence","")
        basis=row.get("accounting_basis","")
        consolidation=row.get("consolidation","")
        if (status=="VERIFIED" and proof in VALID_DATE_PROOF
                and basis in VALID_BASES and basis!="UNSPECIFIED"
                and consolidation=="CONSOLIDATED"):
            eligible.append({k:row.get(k,"") for k in INPUT_COLUMNS})
        elif not row.get("derivation"):
            audit.append(dict(symbol=row["symbol"],metric=row["metric"],
                              period_end=row["period_end"],status="PENDING_REVIEW",
                              reason="Not eligible: missing independent publication proof, basis or consolidation"))
    return staged,eligible,audit


def read(path):
    p=Path(path)
    if not p.exists():
        return []
    with p.open(newline="",encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def main(argv=None):
    parser=argparse.ArgumentParser(description="Generic financial evidence staging; no issuer-specific rules")
    parser.add_argument("--direct",default="research/v6_financial_evidence.csv")
    parser.add_argument("--ytd",default="research/v6_financial_ytd.csv")
    parser.add_argument("--prefix",default=".cache/v6_financial_evidence")
    args=parser.parse_args(argv)
    staged,eligible,audit=stage(read(args.direct),read(args.ytd))
    write_csv(args.prefix+"_staged.csv",staged,EVIDENCE_COLUMNS)
    write_csv(args.prefix+"_eligible.csv",eligible,INPUT_COLUMNS)
    write_csv(args.prefix+"_audit.csv",audit,AUDIT_COLUMNS)
    p=Path(args.prefix+"_summary.json")
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps({"staged":len(staged),"eligible":len(eligible),
                             "status":dict(Counter(r["status"] for r in audit)),
                             "policy":"No inferred publication dates; incomplete evidence never auto-VERIFIED"},
                            indent=2)+"\n",encoding="utf-8")
    print(f"Financial evidence: {len(staged)} staged; {len(eligible)} eligible; review required for rest")


if __name__=="__main__":
    main()
