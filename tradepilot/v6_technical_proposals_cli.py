"""Read-only research proposals for candidates selected by the real TradePilot scanner.

This is a prototype technical detector, NOT integration with the legacy strategy
engine and NOT a verified close or a trading signal. No orders are sent.
"""
import argparse
import json
import math
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from tradepilot.v6_actual_scanner_report_cli import report
from tradepilot.v6_stop_target_cli import write_csv

COLUMNS = ("symbol","market","scanner_score","classification","pattern","entry",
           "target","stop","estimated_net_pct","bar_date","bars_used","reason")
MARKET_TZ = {"US":"America/New_York","MX":"America/Mexico_City"}
DAILY_INTERVALS = {"1d","daily","1day"}


def _utc(value):
    try:
        value = datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return value.astimezone(timezone.utc) if value.tzinfo else None
    except (ValueError, TypeError):
        return None


def _finite(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _bars(conn, symbol, market, as_of):
    """Only dated, positive, consistent daily OHLC bars from the scanner's DB."""
    tz = ZoneInfo(MARKET_TZ[market])
    raw = conn.execute(
        "SELECT interval,bar_end_utc,source,fetched_at_utc,open,high,low,close,volume "
        "FROM market_data_observations WHERE symbol=? ORDER BY bar_end_utc",
        (symbol,)).fetchall()
    by_day = {}
    for item in raw:
        r = dict(item)
        if str(r["interval"]).lower() not in DAILY_INTERVALS:
            continue
        end = _utc(r["bar_end_utc"])
        fetched = _utc(r["fetched_at_utc"])
        if end is None or fetched is None or not r["source"]:
            continue
        day = end.astimezone(tz).date()
        if day > date.fromisoformat(as_of) or fetched < end:
            continue
        o,h,l,c = (_finite(r[k]) for k in ("open","high","low","close"))
        if any(x is None or x <= 0 for x in (o,h,l,c)) or not l <= min(o,c) <= max(o,c) <= h:
            continue
        # Never mix different intraday bars or choose duplicate providers silently.
        by_day.setdefault(day, []).append(dict(day=day,open=o,high=h,low=l,close=c,
                                                source=r["source"],end=end))
    if any(len(rows) != 1 for rows in by_day.values()):
        return [], "AMBIGUOUS_DAILY_BARS"
    return [by_day[d][0] for d in sorted(by_day)], ""


def _prototype_pattern(bars):
    """Illustrative rules only. Replace with existing strategy detector before READY."""
    if len(bars) < 21:
        return None
    today = bars[-1]
    previous = bars[-21:-1]
    highs = [b["high"] for b in previous]
    lows = [b["low"] for b in previous]
    avg_close = sum(b["close"] for b in previous) / len(previous)
    if today["close"] > max(highs):
        return "BREAKOUT", min(lows[-5:])
    if today["low"] <= min(lows[-10:]) * 1.01 and today["close"] > today["open"]:
        return "SUPPORT_BOUNCE", min(today["low"],min(lows[-5:]))
    if today["close"] > avg_close and today["low"] <= avg_close and today["close"] > today["open"]:
        return "PULLBACK", min(lows[-5:])
    return None


def proposals(db_path, as_of, top=20, fee_rate=0.003, net_target=0.03):
    if not 0 <= fee_rate < 1 or not 0 < net_target < 1:
        raise ValueError("Invalid fee or net target")
    ranked, scanner = report(db_path, as_of, limit=top)
    results = []
    reasons = Counter()
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri()+"?mode=ro",uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        for candidate in ranked:
            market = str(candidate["exchange_code"]).upper()
            result = dict(symbol=candidate["symbol"],market=market,
                          scanner_score=candidate["opportunity_score"],
                          classification="WATCHING",pattern="",entry="",target="",stop="",
                          estimated_net_pct="",bar_date="",bars_used=0,reason="")
            if market not in MARKET_TZ:
                result["reason"] = "UNKNOWN_MARKET"
            else:
                bars, error = _bars(conn,candidate["symbol"],market,as_of)
                result["bars_used"] = len(bars)
                if error:
                    result["reason"] = error
                elif not bars or bars[-1]["day"] != date.fromisoformat(as_of):
                    result["reason"] = "NO_DATED_DAILY_BAR_FOR_SESSION"
                else:
                    result["bar_date"] = bars[-1]["day"].isoformat()
                    pattern = _prototype_pattern(bars)
                    if pattern is None:
                        result["reason"] = "NO_PROTOTYPE_PATTERN_OR_INSUFFICIENT_HISTORY"
                    else:
                        name,stop = pattern
                        entry = bars[-1]["close"]
                        # Buy and sell fee modeled as fraction of notional on each side.
                        target = entry * (1 + fee_rate) * (1 + net_target) / (1 - fee_rate)
                        if not 0 < stop < entry < target:
                            result["reason"] = "INVALID_STRUCTURAL_STOP"
                        else:
                            result.update(pattern=name,entry=round(entry,6),
                                          target=round(target,6),stop=round(stop,6),
                                          estimated_net_pct=round(((target*(1-fee_rate)/
                                                                    (entry*(1+fee_rate)))-1)*100,4),
                                          reason="PROTOTYPE_ONLY_EOD_UNVERIFIED")
            reasons[result["reason"]] += 1
            results.append(result)
    summary = dict(as_of=as_of,scanner_status=scanner["status"],
                   scanner_candidates=scanner.get("scanner_candidates",0),
                   candidates_evaluated=len(results),patterns_computed=sum(bool(r["pattern"]) for r in results),
                   ready=0,status="RESEARCH_ONLY",reasons=dict(reasons),
                   limitations=["Scanner chooses every symbol; no manual ticker injection",
                                "Prototype patterns are not existing TradePilot strategy confirmations",
                                "A daily bar timestamp does not independently prove official final close",
                                "No holiday or shortened-session calendar verification",
                                "Fee rate is an assumption, not verified GBM tariff",
                                "All proposals WATCHING; never READY and no orders"])
    return results,summary


def main(argv=None):
    parser=argparse.ArgumentParser(description="Read-only prototype technical proposals for real scanner candidates")
    parser.add_argument("--db",default="data/tradepilot.db")
    parser.add_argument("--as-of",required=True)
    parser.add_argument("--top",type=int,default=20)
    parser.add_argument("--fee-rate",type=float,default=0.003)
    parser.add_argument("--net-target",type=float,default=0.03)
    parser.add_argument("--prefix",default=".cache/v6_technical_proposals")
    args=parser.parse_args(argv)
    rows,summary=proposals(args.db,args.as_of,args.top,args.fee_rate,args.net_target)
    write_csv(args.prefix+"_candidates.csv",rows,COLUMNS)
    path=Path(args.prefix+"_summary.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,ensure_ascii=False))
    for row in rows:
        print(f"{row['symbol']}: {row['classification']} {row['pattern']} {row['reason']}")
    if not rows:
        print("ABSTAIN: no qualifying post-close scanner candidates")


if __name__=="__main__":
    main()
