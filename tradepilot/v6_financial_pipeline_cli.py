"""One-command, issuer-agnostic TradePilot financial evidence and score pipeline."""
import argparse
from tradepilot.v6_financial_evidence_cli import main as evidence_main
from tradepilot.v6_financial_engine_cli import main as engine_main


def main(argv=None):
    parser=argparse.ArgumentParser(description="Run generic financial staging and US/MX quality research")
    parser.add_argument("--cases",default=".cache/v6_pilot_cases.csv")
    parser.add_argument("--us-trends",default=".cache/v6_financial_trends.csv")
    parser.add_argument("--direct",default="research/v6_financial_evidence.csv")
    parser.add_argument("--ytd",default="research/v6_financial_ytd.csv")
    args=parser.parse_args(argv)
    evidence_main(["--direct",args.direct,"--ytd",args.ytd])
    engine_main(["--cases",args.cases,"--us-trends",args.us_trends,
                 "--mx-observations",".cache/v6_financial_evidence_eligible.csv"])
    print("Generic evidence + financial quality pipeline complete. No production trading changes.")


if __name__=="__main__":
    main()
