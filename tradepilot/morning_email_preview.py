"""Readable offline daily research email. Does not send messages or place trades."""
from __future__ import annotations
import argparse
import json
from datetime import datetime
from html import escape
from pathlib import Path


def fmt(value, digits=2):
    try:
        return f"{float(value):,.{digits}f}" if value is not None else "—"
    except (TypeError, ValueError, OverflowError):
        return "—"


def label(state):
    return {
        "CONFIRMED_RESEARCH": "Ruptura confirmada al cierre",
        "BREAKOUT_PENDING_CONFIRMATION": "Ruptura pendiente de confirmar",
        "APPROACHING": "Cerca de resistencia",
        "REBOUND_CONFIRMED_RESEARCH": "Rebote confirmado al cierre",
        "REBOUND_SETUP": "Rebote en formación",
        "REBOUND_WATCH": "Cerca de soporte",
    }.get(state, "En observación")


def opportunity_card(row, strategy, currency):
    plan = row.get("trade_plan") or {}
    diag = row.get("risk_diagnostics") or {}
    ratio = plan.get("reward_risk_net")
    good = row.get("risk_assessment") == "RISK_ACCEPTABLE_FOR_RESEARCH"
    # Highlight only technically confirmed setups that ALSO pass the risk gate.
    # Technical score alone is never a buy signal.
    confirmed = row.get("state") in ("CONFIRMED_RESEARCH", "REBOUND_CONFIRMED_RESEARCH")
    standout = bool(good and confirmed)
    color = "#17704b" if good else "#a34e26"
    border = "#16865a" if standout else "#e0e7f0"
    background = "#f0fbf5" if standout else "#fff"
    level_key, level_name = ("resistance", "Resistencia") if strategy == "breakout" else ("support", "Soporte")
    pairs = [
        ("Cierre EOD", row.get("reference_close")), (level_name, row.get(level_key)),
        ("Entrada*", plan.get("entry_reference")), ("Objetivo*", plan.get("target_exit_reference")),
        ("Stop*", plan.get("stop_reference")), ("R/B", ratio)]
    lines = ['<tr>' + ''.join(
        '<td style="width:16.66%;padding:9px 7px 9px 0;vertical-align:top;white-space:nowrap;">'
        '<div style="font-size:10px;color:#66788b;">' + escape(k) + '</div>'
        '<div style="font-size:16px;font-weight:bold;">' + fmt(v) + '</div></td>'
        for k, v in pairs) + '</tr>']
    why = ("El stop está a " + fmt(diag.get("distance_entry_to_stop_pct")) +
           "% de la entrada. R/B " + fmt(ratio) + " es inferior al mínimo de 1.00.") if not good and ratio is not None else (
           "Cumple el filtro R/B ≥ 1.00." if good else "Faltan datos para evaluar el riesgo.")
    indicators = ("RSI14 " + fmt(row.get("rsi14")) + " · Volumen " + fmt(row.get("relative_volume")) + "x") if strategy == "rebound" else (
        "Volumen " + fmt(row.get("relative_volume")) + "x · Score " + fmt(row.get("quality_score"), 1) + "/100")
    return ('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="border:2px solid ' + border + ';background:' + background + ';margin:0 0 12px;border-collapse:separate;">' +
            '<tr><td style="padding:14px 16px;">'
            ('<div style="font-size:12px;font-weight:bold;color:#17704b;margin-bottom:8px;">&#9733; SEÑAL DESTACADA · CONFIRMADA Y CON RIESGO ACEPTABLE</div>' if standout else '') +
            '<div style="font-size:18px;font-weight:bold;color:#182b4c;">' + escape(str(row.get("symbol", ""))) + '</div>'
            '<div style="font-size:12px;color:#607087;margin:4px 0 8px;">' +
            escape(label(row.get("state"))) + ' · ' + escape(str(row.get("session", "—"))) +
            ' · ' + escape(currency) + '</div>'
            '<div style="font-size:12px;font-weight:bold;color:' + color + ';">' +
            ("Pasa filtro de riesgo" if good else "Solo seguimiento · riesgo desfavorable") + '</div>'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">' + ''.join(lines) + '</table>'
            '<div style="font-size:12px;color:#465b70;margin:8px 0;">' + indicators + '</div>'
            '<div style="font-size:12px;color:' + color + ';background:#f6f8fb;padding:9px;">' +
            why + '</div></td></tr></table>')


def render_html(report):
    stamp = str(report.get("as_of_utc", ""))
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M UTC")
    except ValueError:
        when = stamp
    parts = [
        '<!doctype html><html lang="es"><head><meta charset="utf-8"></head>',
        '<body style="margin:0;background:#f0f3f8;font-family:Arial,Helvetica,sans-serif;color:#182333;">',
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">',
        '<table role="presentation" width="960" cellpadding="0" cellspacing="0" style="width:100%;max-width:960px;background:#fff;">',
        '<tr><td style="padding:24px;background:#1b2c4f;color:#fff;">'
        '<div style="font-size:12px;letter-spacing:2px;color:#c6d8f0;">TRADEPILOT</div>'
        '<h1 style="font-size:25px;margin:9px 0;color:#fff;">Radar diario de oportunidades</h1>'
        '<div style="font-size:12px;color:#c6d8f0;">México y Estados Unidos · ' + escape(when) + '</div>'
        '</td></tr><tr><td style="padding:20px 22px;">',
        '<p style="font-size:13px;line-height:1.5;color:#53647a;">'
        '<b>Resumen basado en el último cierre diario completo.</b> No contiene cotizaciones en vivo. '
        'Los precios de entrada, objetivo y stop son escenarios de investigación, no órdenes.</p>',
    ]
    for market, heading, currency in (("MX", "México", "MXN"), ("US", "Estados Unidos", "USD")):
        data = report.get("markets", {}).get(market, {})
        rebounds = data.get("rebounds", {})
        primary = len(data.get("primary", [])) + len(rebounds.get("primary", []))
        parts.append('<h2 style="font-size:21px;color:#1b2c4f;margin:27px 0 8px;border-bottom:2px solid #e0e7f0;padding-bottom:9px;">' +
                     heading + ' · ' + currency + '</h2>')
        parts.append('<p style="font-size:13px;color:#566b81;"><b>' + str(data.get("reviewed", 0)) +
                     ' instrumentos revisados</b> · ' + str(data.get("current", 0)) +
                     ' con cierre vigente · ' + str(primary) + ' candidatos que pasan el filtro</p>')
        if not primary:
            parts.append('<p style="font-size:12px;color:#855227;background:#fff7e9;padding:12px;">'
                         'Ninguna señal supera hoy todos los filtros de riesgo. Las siguientes acciones son '
                         'para seguimiento, no recomendaciones de compra.</p>')
        for strategy, title, group in (
            ("breakout", "Rupturas de resistencia", data),
            ("rebound", "Rebotes desde soporte", rebounds)):
            parts.append('<h3 style="font-size:17px;color:#203656;margin:22px 0 9px;">' + title + '</h3>')
            for tier, subtitle in (("primary", "Cumplen los filtros"), ("watch", "En observación")):
                items = group.get(tier, [])
                if not items:
                    if tier == "primary":
                        continue
                    parts.append('<p style="font-size:12px;color:#697a8b;">Sin señales en observación.</p>')
                    continue
                parts.append('<div style="font-size:12px;font-weight:bold;color:#52647a;margin:12px 0 8px;">' +
                             subtitle + ' (' + str(len(items)) + ')</div>')
                for row in items:
                    parts.append(opportunity_card(row, strategy, currency))
    parts.extend([
        '<p style="font-size:11px;color:#65758a;line-height:1.5;margin-top:24px;">'
        '* Niveles hipotéticos calculados con objetivo de 3% neto estimado, comisiones y deslizamiento supuestos. '
        'R/B = beneficio/riesgo neto estimado; mínimo provisional 1.00. '
        'El score técnico no es una probabilidad de éxito. No se realizaron operaciones ni se enviaron correos.</p>',
        '</td></tr></table></td></tr></table></body></html>'])
    return "\n".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create an offline HTML email preview; no mail is sent")
    parser.add_argument("--input", default="morning_radar_report.json")
    parser.add_argument("--output", default="morning_radar_email_preview.html")
    args = parser.parse_args(argv)
    report = json.loads(Path(args.input).read_text(encoding="utf-8"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(report), encoding="utf-8")
    print(f"HTML preview saved: {output} (no email sent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
