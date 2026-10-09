"""Safe offline Gmail report preview. Does not connect to Gmail or send mail."""
from __future__ import annotations
import argparse
from html import escape
import json
from pathlib import Path


def render_html(report):
    rows = ['<html><body style="font-family:Arial,sans-serif">',
            '<h2>TradePilot | Daily Opportunity Radar</h2>',
            '<p>Research only. Last completed daily close; NOT a live intraday quote. '
            'Prices and plans are illustrative, not orders. Scores are NOT win probabilities.</p>',
            '<p>Generated: ' + escape(str(report.get("as_of_utc", "unknown"))) + '</p>']
    for market, name in (("MX", "Mexico (MXN)"), ("US", "United States (USD)")):
        data = report.get("markets", {}).get(market, {})
        rows.append('<h3>' + name + '</h3>')
        rows.append('<p>Reviewed: ' + str(data.get("reviewed", 0)) +
                    ' | Current EOD data: ' + str(data.get("current", 0)) + '</p>')
        for tier, title in (("primary", "Confirmed research (max 10)"),
                            ("watch", "Watchlist (max 3)")):
            rows.append('<h4>' + title + '</h4>')
            items = data.get(tier, [])
            if not items:
                rows.append('<p>No candidates.</p>')
                continue
            rows.append('<table border="1" cellpadding="6" cellspacing="0"><tr>' +
                        ''.join('<th>' + x + '</th>' for x in
                                ("Symbol", "Bar date", "Daily close", "Breakout", "Entry",
                                 "Target", "Stop", "Net target %", "R/R", "Score", "State")) + '</tr>')
            for r in items:
                plan = r.get("trade_plan") or {}
                values = (r.get("symbol"), r.get("session"), r.get("reference_close"),
                          r.get("breakout_trigger"), plan.get("entry_reference"),
                          plan.get("target_exit_reference"), plan.get("stop_reference"),
                          plan.get("estimated_net_target_pct"), plan.get("reward_risk_net"),
                          r.get("quality_score"), r.get("state"))
                rows.append('<tr>' + ''.join('<td>' + escape(str(v if v is not None else "N/A")) +
                                            '</td>' for v in values) + '</tr>')
            rows.append('</table>')
    rows.append('<p>Source: completed EOD candles. No broker execution, no verified live prices. '
                'Daily scan coverage and data freshness must be checked before use.</p></body></html>')
    return '\n'.join(rows)


def main(argv=None):
    p = argparse.ArgumentParser(description="Generate offline HTML preview; NEVER sends email")
    p.add_argument("--input", default="morning_radar_report.json")
    p.add_argument("--output", default="morning_radar_email_preview.html")
    args = p.parse_args(argv)
    report = json.loads(Path(args.input).read_text(encoding="utf-8"))
    Path(args.output).write_text(render_html(report), encoding="utf-8")
    print(f"HTML preview saved: {args.output} (no email sent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
