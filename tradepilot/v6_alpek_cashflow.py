"""Alpek 3Q operating cash flow: official consolidated 9M less 6M YTD.

Sources: Alpek unaudited consolidated financial statements, page 3:
9M: https://www.alpek.com/wp-content/uploads/2022/11/Alpek-3Q22-Unaudited-Consolidated-Financial-Statements.pdf
6M: https://www.alpek.com/wp-content/uploads/2022/08/Alpek-2Q22-Unaudited-Consolidated-Financial-Statements.pdf
Values are in millions MXN. Document availability is assessed conservatively
as 2022-11-30 for 9M and 2022-08-31 for 6M, based on archive upload
month, NOT a proven exact publication date. These are upper-bound
research assumptions, not verified filing timestamps. Both precede
the pilot signal 2022-12-20.
"""
from datetime import date

SOURCE_9M = "https://www.alpek.com/wp-content/uploads/2022/11/Alpek-3Q22-Unaudited-Consolidated-Financial-Statements.pdf"
SOURCE_6M = "https://www.alpek.com/wp-content/uploads/2022/08/Alpek-2Q22-Unaudited-Consolidated-Financial-Statements.pdf"

YTD = {
    2022: {"nine_month": 9948, "six_month": 7405},
    2021: {"nine_month": 7378, "six_month": 6755},
}


def operating_cash_flow_rows():
    rows = []
    for year, values in sorted(YTD.items()):
        quarter = values["nine_month"] - values["six_month"]
        rows.append({
            "symbol": "ALPEKA.MX", "metric": "operating_cash_flow",
            "period_start": f"{year}-07-01", "period_end": f"{year}-09-30",
            "published_at": "2022-11-30", "value": str(quarter),
            "currency": "MXN", "scale": "1000000",
            "source_url": SOURCE_9M, "source_page": "3",
            "verification_status": "VERIFIED",
        })
    return rows


def evidence_details():
    return {
        "method": "quarter = nine_month_ytd - six_month_ytd",
        "units": "millions MXN",
        "consolidated": True,
        "statement_page": 3,
        "nine_month_source": SOURCE_9M,
        "six_month_source": SOURCE_6M,
        "nine_month_values": {str(y): v["nine_month"] for y, v in YTD.items()},
        "six_month_values": {str(y): v["six_month"] for y, v in YTD.items()},
        "quarter_values": {str(y): v["nine_month"] - v["six_month"] for y, v in YTD.items()},
        "publication_date_caveat": (
            "The 2022-11-30 date is a conservative end-of-upload-month "
            "proxy based on the URL path, not a confirmed filing date. "
            "Issuer results event dated 2022-10-20. Source PDF URL is "
            "under /2022/11/. Verify actual document availability before "
            "promoting evidence to production-grade PIT."
        ),
        "eligible_for_signal_date": "2022-12-20",
    }
