"""One-command reproducible ALSEA research pipeline (no production scoring)."""
import argparse
from pathlib import Path

from tradepilot.v6_mx_structured_cli import main as structured_main
from tradepilot.v6_mx_alsea_comparison_cli import main as comparison_main
from tradepilot.v6_mx_alsea_three_metric_cli import main as three_metric_main


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--skip-download",action="store_true",
                        help="Reuse existing structured PDF rows")
    args=parser.parse_args(argv)
    if not args.skip_download:
        structured_main([])
    source=Path(".cache/v6_mx_structured_rows.csv")
    if not source.exists():
        raise FileNotFoundError(f"Missing {source}; run without --skip-download")
    comparison_main([])
    three_metric_main([])
    print("Research pipeline completed. All observations pending; no production scores changed.")


if __name__=="__main__":
    main()
