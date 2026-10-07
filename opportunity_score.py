from config import OPPORTUNITY_SCORE

def calculate_opportunity_score(metrics: dict, quality_passed: bool) -> dict:
    weights = OPPORTUNITY_SCORE["weights"]
    rsi = metrics.get("rsi")
    rvol = metrics.get("rvol")
    atr = metrics.get("atr_pct")

    trend_points = weights["trend"] if metrics.get("trend") == "Bullish" else 0

    rsi_points = 0
    if rsi is not None:
        if 50 <= rsi <= 65:
            rsi_points = weights["rsi"]
        elif 40 <= rsi < 50:
            rsi_points = weights["rsi"] * 0.65
        elif 65 < rsi <= 75:
            rsi_points = weights["rsi"] * 0.55

    rvol_points = 0
    if rvol is not None:
        if rvol >= 1.5:
            rvol_points = weights["rvol"]
        elif rvol >= 1.0:
            rvol_points = weights["rvol"] * 0.70
        elif rvol >= 0.70:
            rvol_points = weights["rvol"] * 0.35

    atr_points = 0
    if atr is not None:
        if 2.0 <= atr <= 4.5:
            atr_points = weights["atr"]
        elif 1.0 <= atr < 2.0:
            atr_points = weights["atr"] * 0.55
        elif 4.5 < atr <= 6.0:
            atr_points = weights["atr"] * 0.60

    components = {
        "trend": trend_points,
        "rsi": rsi_points,
        "rvol": rvol_points,
        "atr": atr_points,
    }
    score = round(sum(components.values()), 1) if quality_passed else 0.0
    return {"score": score, "eligible": quality_passed, "components": components}
