"""Safe offline Gmail report preview. Does not connect to Gmail or send mail."""
from __future__ import annotations
import argparse
from html import escape
import json
from pathlib import Path
from tradepilot.morning_report import risk_label


def fmt(value, digits=2):
    if value is None:
        return "—"
    try:
        return f"{float(value):,.{digits}f}"
    except (ValueError, TypeError):
        return escape(str(value))


def render_html(report):
    """Inline styles and table layout for common Gmail/Outlook clients."""
    css = "font-family:Arial,Helvetica,sans-serif;color:#182333;"
    parts = ['<!doctype html><html><head><meta charset="utf-8"></head>',
             '<body style="margin:0;background:#f3f6fa;' + css + '">',
             '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">',
             '<table role="presentation" width="760" cellpadding="0" cellspacing="0" style="max-width:760px;width:100%;background:#ffffff;">',
             '<tr><td style="background:#142b4b;color:white;padding:26px 24px;">',
             '<div style="font-size:13px;letter-spacing:2px;color:#b8cde9;">TRADEPILOT</div>',
             '<h1 style="margin:8px 0;font-size:25px;color:#ffffff;">Daily Opportunity Radar</h1>',
             '<div style="font-size:13px;color:#cbd9e9;">Mexico + United States | ' +
             escape(str(report.get("as_of_utc", "unknown"))) + '</div></td></tr>',
             '<tr><td style="padding:18px 24px;">',
             '<p style="font-size:13px;color:#58677a;">Research only. The displayed price is the last completed daily close, <b>not a live quote</b>. Entry, target and stop are hypothetical references, not executable orders.</p>']
    for market, name in (("MX", "🇲🇽 México · MXN"), ("US", "🇺🇸 Estados Unidos · USD")):
        data = report.get("markets", {}).get(market, {})
        parts.append('<h2 style="font-size:20px;margin:24px 0 6px;border-bottom:2px solid #dce5f0;padding-bottom:9px;">' + name + '</h2>')
        parts.append('<p style="font-size:12px;color:#63758a;">Revisados: ' + str(data.get("reviewed", 0)) +
                     ' · Datos EOD vigentes: ' + str(data.get("current", 0)) +
                     ' · Riesgo descartado: ' + str(data.get("risk_filtered", 0)) + '</p>')
        for tier, title in (("primary", "Candidatas principales · máximo 10"),
                            ("watch", "En observación · máximo 3")):
            items = data.get(tier, [])
            parts.append('<h3 style="font-size:15px;margin:22px 0 9px;">' + title + '</h3>')
            if not items:
                parts.append('<p style="font-size:13px;color:#63758a;">Sin oportunidades que cumplan las condiciones.</p>')
                continue
            parts.append('<table width="100%" cellpadding="7" cellspacing="0" style="border-collapse:collapse;font-size:12px;">')
            parts.append('<tr style="background:#eaf0f7;text-align:right;">' +
                         '<th style="text-align:left;">Símbolo</th><th>Cierre*</th><th>Ruptura</th><th>Entrada*</th><th>Salida*</th><th>Stop*</th><th>R/B</th><th>Score</th></tr>')
            for index, row in enumerate(items):
                plan = row.get("trade_plan") or {}
                values = (row.get("reference_close"), row.get("breakout_trigger"),
                          plan.get("entry_reference"), plan.get("target_exit_reference"),
                          plan.get("stop_reference"))
                cells = ''.join('<td style="padding:8px 5px;text-align:right;border-bottom:1px solid #e6ecf2;">' + fmt(v) + '</td>' for v in values)
                ratio = plan.get("reward_risk_net")
                risk_color = "#a53a26" if risk_label(row) != "RISK_ACCEPTABLE_FOR_RESEARCH" else "#227451"
                parts.append('<tr style="background:' + ('#ffffff' if index % 2 == 0 else '#f8fafc') + ';">' +
                             '<td style="font-weight:bold;border-bottom:1px solid #e6ecf2;">' + escape(str(row.get("symbol", ""))) + '</td>' +
                             cells + '<td style="text-align:right;color:' + risk_color + ';">' + fmt(ratio) +
                             '</td><td style="text-align:right;">' + fmt(row.get("quality_score"), 1) + '</td></tr>')
                status = {"APPROACHING": "Cerca de resistencia",
                          "BREAKOUT_PENDING_CONFIRMATION": "Ruptura sin confirmar",
                          "CONFIRMED_RESEARCH": "Confirmación histórica"}.get(row.get("state"), "Sin clasificar")
                warning = " · Riesgo/beneficio desfavorable" if risk_label(row) == "UNFAVORABLE_RISK_REWARD" else ""
                parts.append('<tr><td colspan="8" style="font-size:11px;color:#607287;padding:3px 6px 12px;">' +
                             escape(status + warning + " · Vela: " + str(row.get("session", "N/A"))) + '</td></tr>')
            parts.append('</table>')
        rebound=data.get("rebounds",{})
        parts.append('<h3 style="font-size:17px;">Posibles rebotes · soporte y recuperación</h3>')
        for tier,title in (("primary","Rebotes principales · máximo 10"),("watch","Rebotes en observación · máximo 3")):
            parts.append('<h4>'+title+'</h4>')
            items=rebound.get(tier,[])
            if not items:
                parts.append('<p>Sin candidatos que cumplan las condiciones.</p>')
            for row in items:
                plan=row.get("trade_plan") or {}
                parts.append('<p><b>'+escape(str(row.get("symbol","")))+'</b> · Cierre EOD: '+fmt(row.get("reference_close"))+
                    ' · Soporte: '+fmt(row.get("support"))+' · RSI14: '+fmt(row.get("rsi14"))+
                    ' · RVOL: '+fmt(row.get("relative_volume"))+' · Entrada*: '+fmt(plan.get("entry_reference"))+
                    ' · Objetivo*: '+fmt(plan.get("target_exit_reference"))+' · Stop*: '+fmt(plan.get("stop_reference"))+
                    ' · R/B: '+fmt(plan.get("reward_risk_net"))+' · '+escape(str(row.get("state","")))+
                    ' · '+escape(str(row.get("risk_assessment","")))+'</p>')
    parts.extend(['<p style="font-size:11px;color:#66778b;margin-top:25px;">* Entrada, salida y stop son referencias hipotéticas; no cotizaciones actuales ni garantías de ejecución. Objetivo de 3% neto estimado con comisiones y deslizamiento supuestos. R/B = beneficio/riesgo neto estimado. Umbral R/B ≥ 1.0 provisional, sin validación histórica. El score no es probabilidad de éxito. La cobertura depende del universo analizado.</p>',
                  '<p style="font-size:11px;color:#66778b;">No se enviaron correos ni se realizaron operaciones.</p>',
                  '</td></tr></table></td></tr></table></body></html>'])
    return "\n".join(parts)


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
