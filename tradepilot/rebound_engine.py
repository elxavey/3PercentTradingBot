"""Research-only daily rebound radar; never submits orders."""
from datetime import datetime, timezone
import pandas as pd
from tradepilot.breakout_session_quality import assess_daily_sessions
from tradepilot.breakout_trade_plan import build_trade_plan

def clean_placeholders(df):
    if df is None or df.empty:
        return df, []
    cols=["Open","High","Low","Close"]
    if not all(c in df for c in cols+["Volume"]):
        return df, []
    mask=df[cols].isna().all(axis=1) & pd.to_numeric(df["Volume"],errors="coerce").eq(0)
    return df.loc[~mask].copy(),[str(i)[:10] for i in df.index[mask]]

def analyze_rebound(symbol, history, *, as_of_utc=None):
    now=as_of_utc or datetime.now(timezone.utc)
    market="MX" if symbol.endswith(".MX") else "US"
    floor=5_000_000 if market=="MX" else 10_000_000
    if history is None or not isinstance(history,pd.DataFrame) or history.empty:
        return {"symbol":symbol,"state":"REJECT","reason":"NO_HISTORY"}
    data=history.copy()
    if isinstance(data.index,pd.DatetimeIndex):
        data=data.loc[pd.to_datetime(data.index,utc=True).date<now.date()]
    data,removed=clean_placeholders(data)
    base={"symbol":symbol,"removed_empty_price_placeholders":removed,"actionable":False}
    if len(data)<60 or not isinstance(data.index,pd.DatetimeIndex):
        return {**base,"state":"REJECT","reason":"INSUFFICIENT_HISTORY"}
    quality=assess_daily_sessions(data,market=market,as_of_utc=now)
    if quality["state"]!="CURRENT":
        return {**base,"state":"REJECT","reason":quality.get("reason","STALE"),"session_quality":quality}
    fields=["Open","High","Low","Close","Volume"]
    if not all(c in data for c in fields):
        return {**base,"state":"REJECT","reason":"MISSING_OHLCV"}
    d=data[fields].tail(60).apply(pd.to_numeric,errors="coerce")
    if not d.notna().all().all() or (d[fields[:4]]<=0).any().any() or (d.Volume<0).any():
        return {**base,"state":"REJECT","reason":"INVALID_OHLCV"}
    tol=d[fields[:4]].abs().max(axis=1)*1e-12
    if (d.High+tol<d[["Open","Low","Close"]].max(axis=1)).any() or (d.Low-tol>d[["Open","High","Close"]].min(axis=1)).any():
        return {**base,"state":"REJECT","reason":"INVALID_OHLCV"}
    turnover=float((d.Close.tail(20)*d.Volume.tail(20)).mean())
    if turnover<floor:
        return {**base,"state":"REJECT","reason":"LOW_OR_INVALID_TURNOVER","avg_turnover_20d_local_currency":turnover}
    price=float(d.Close.iloc[-1]);support=float(d.Low.iloc[-21:-1].min())
    distance=100*(price/support-1)
    diff=d.Close.diff()
    gains=diff.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    losses=(-diff.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rsi=100.0 if losses.iloc[-1]==0 else float(100-100/(1+gains.iloc[-1]/losses.iloc[-1]))
    sma20=float(d.Close.tail(20).mean())
    baseline=float(d.Volume.iloc[-21:-1].mean())
    rvol=float(d.Volume.iloc[-1]/baseline) if baseline>0 else 0
    near=-1<=distance<=5
    rising=price>float(d.Close.iloc[-2]) and price>=float(d.Open.iloc[-1])
    confirmed=near and rising and price>sma20 and rvol>=1.2 and 35<=rsi<=65
    state="REBOUND_CONFIRMED_RESEARCH" if confirmed else ("REBOUND_SETUP" if near and rising else ("REBOUND_WATCH" if near else "MONITORING"))
    trigger=max(price,float(d.High.iloc[-1]))*1.001
    stop=support*0.995
    plan=build_trade_plan({"reference_close":price,"breakout_trigger":trigger,"structural_stop_reference":stop}) if 0<stop<trigger else {}
    score=round(35*max(0,1-abs(distance)/5)+20*int(rising)+20*int(rvol>=1.2)+15*int(35<=rsi<=65)+10*int(price>sma20),2)
    return {**base,"state":state,"session_quality":quality,"session":str(data.index[-1])[:10],
            "reference_close":price,"support":round(support,4),"distance_to_support_pct":round(distance,3),
            "rsi14":round(rsi,2),"sma20":round(sma20,4),"relative_volume":round(rvol,3),
            "rebound_trigger":round(trigger,4),"quality_score":score,"trade_plan":plan,
            "avg_turnover_20d_local_currency":round(turnover,2)}
