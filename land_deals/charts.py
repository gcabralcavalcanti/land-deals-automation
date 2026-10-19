"""Static outputs: PNG charts, the PDF report (matplotlib) and the HTML dashboard (Chart.js, no build step)."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from . import config  # noqa: E402
from .workbook import month_label  # noqa: E402

BLUE, ORANGE, GREY, GREEN, RED = "#1f4e5f", "#e07b39", "#9aa5ab", "#3c8d5a", "#b8433a"
MI = FuncFormatter(lambda v, _: f"{v / 1e6:,.1f}")


def _money(v):
    return f"R$ {v / 1e6:,.1f} mi"


def _tex(s: str) -> str:
    """matplotlib reads $...$ as math; escape the currency sign."""
    return s.replace("$", r"\$")


def _pct(v):
    return "n/a" if v is None else f"{v:.1%}"


def _align_zero(ax, a, ax2, b):
    """Put zero at the same height on both y axes."""
    a_lo, a_hi = min(min(a), 0) * 1.1, max(max(a), 0) * 1.1
    b_lo, b_hi = min(min(b), 0) * 1.1, max(max(b), 0) * 1.1
    f = max(-a_lo / (a_hi - a_lo), -b_lo / (b_hi - b_lo))          # share of the axis below zero
    a_lo, b_lo = -f * a_hi / (1 - f), -f * b_hi / (1 - f)
    a_lo, b_lo = min(a_lo, min(a) * 1.1), min(b_lo, min(b) * 1.1)
    ax.set_ylim(a_lo, -a_lo * (1 - f) / f if f else a_hi)
    ax2.set_ylim(b_lo, -b_lo * (1 - f) / f if f else b_hi)


def fig_cash(pf):
    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = pf["months"]
    ax.bar(x, pf["net"], color=[GREEN if v >= 0 else RED for v in pf["net"]], width=0.8, label="monthly net")
    ax2 = ax.twinx()
    ax2.plot(x, pf["cumulative"], color=BLUE, lw=2.2, label="cumulative")
    ax2.axhline(0, color=GREY, lw=0.8)
    ax.set_title("Portfolio cash flow (R$ million)")
    ax.yaxis.set_major_formatter(MI)
    ax2.yaxis.set_major_formatter(MI)
    ticks = x[::12]
    ax.set_xticks(ticks, [month_label(m) for m in ticks], rotation=0, fontsize=8)
    _align_zero(ax, pf["net"], ax2, pf["cumulative"])
    ax2.annotate(_tex(f"max exposure {_money(pf['max_exposure'])}"), (pf["exposure_month"], -pf["max_exposure"]),
                 xytext=(12, 10), textcoords="offset points", fontsize=8, color=BLUE)
    fig.legend(loc="upper left", bbox_to_anchor=(0.07, 0.88), fontsize=8, frameon=False)
    fig.tight_layout()
    return fig


def fig_parcels(pf):
    ps = pf["projects"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4))
    ids = [p["id"] for p in ps]
    a1.barh(ids, [p["npv"] for p in ps], color=[BLUE if p["strategy"] == "subdivision" else ORANGE for p in ps])
    a1.axvline(0, color=GREY, lw=0.8)
    a1.xaxis.set_major_formatter(MI)
    a1.set_title("NPV by parcel (R$ million)\nblue: subdivided, orange: sold whole", fontsize=10)
    a1.invert_yaxis()
    hurdle = config.base()["discount_rate_year"]
    a2.barh(ids, [(p["irr"] or 0) * 100 for p in ps], color=[GREEN if (p["irr"] or 0) >= hurdle else RED for p in ps])
    a2.axvline(hurdle * 100, color=GREY, ls="--", lw=1)
    a2.set_title(f"IRR per year (%) vs {hurdle:.0%} hurdle", fontsize=10)
    a2.invert_yaxis()
    fig.tight_layout()
    return fig


def fig_tornado(sens):
    fig, ax = plt.subplots(figsize=(10, 4))
    names = [s["assumption"] for s in sens][::-1]
    base = sens[0]["base_npv"]
    lows = [s["npv_low"] - base for s in sens][::-1]
    highs = [s["npv_high"] - base for s in sens][::-1]
    ax.barh(names, lows, color=ORANGE, label="assumption at its low value")
    ax.barh(names, highs, color=BLUE, label="assumption at its high value")
    ax.axvline(0, color=GREY, lw=0.8)
    ax.xaxis.set_major_formatter(MI)
    ax.set_title(_tex(f"Sensitivity of portfolio NPV (change vs base {_money(base)}, R$ million)"))
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    fig.tight_layout()
    return fig


def fig_scenarios(scen):
    fig, ax = plt.subplots(figsize=(10, 3.4))
    names = [s["scenario"] for s in scen]
    ax.bar(names, [s["npv"] for s in scen], color=[RED, BLUE, GREEN])
    for i, s in enumerate(scen):
        ax.annotate(f"NPV {_money(s['npv'])}\nIRR {_pct(s['irr'])}", (i, s["npv"]), ha="center",
                    xytext=(0, 4 if s["npv"] >= 0 else -26), textcoords="offset points", fontsize=8)
    ax.axhline(0, color=GREY, lw=0.8)
    ax.yaxis.set_major_formatter(MI)
    ax.set_title("Portfolio NPV by scenario (R$ million)")
    fig.tight_layout()
    return fig


def save_pngs(pf, scen, sens, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, fig in (("cash_flow", fig_cash(pf)), ("parcels", fig_parcels(pf)), ("sensitivity", fig_tornado(sens)),
                      ("scenarios", fig_scenarios(scen))):
        p = out / f"{name}.png"
        fig.savefig(p, dpi=110)
        plt.close(fig)
        paths.append(p)
    return paths


def _text_page(pdf, title: str, lines: list[str]):
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.text(0.08, 0.95, title, fontsize=15, weight="bold", color=BLUE, va="top")
    y = 0.91
    for line in lines:
        bold = line.startswith("## ")
        for part in (textwrap.wrap(line[3:] if bold else line, 100) or [""]):
            fig.text(0.08, y, part, fontsize=11 if bold else 9, weight="bold" if bold else "normal", va="top",
                     parse_math=False)
            y -= 0.03 if bold else 0.02
        if y < 0.05:
            break
    pdf.savefig(fig)
    plt.close(fig)


def pdf_report(path: Path, pf, scen, sens, strat, memos) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    a = config.base()
    lines = [
        "Synthetic data generated by generate_data.py. Every number below is computed by the model in this repository.",
        "",
        "## Portfolio",
        f"{len(pf['projects'])} parcels. VGV {_money(pf['vgv'])} (subdivision {_money(pf['vgv_by_strategy']['subdivision'])}, "
        f"whole-lot resale {_money(pf['vgv_by_strategy']['whole'])}).",
        f"Net profit {_money(pf['profit'])}, margin on VGV {_pct(pf['margin'])}.",
        f"NPV at {a['discount_rate_year']:.0%} a year: {_money(pf['npv'])}. IRR {_pct(pf['irr'])} a year.",
        f"Maximum cash exposure {_money(pf['max_exposure'])} in {month_label(pf['exposure_month'])}; "
        f"payback in {month_label(pf['payback_month']) if pf['payback_month'] is not None else 'not reached'}.",
        "",
        "## Scenarios",
    ] + [f"{s['scenario']:>12}: NPV {_money(s['npv'])}, IRR {_pct(s['irr'])}, max exposure {_money(s['max_exposure'])}"
         for s in scen] + [
        "",
        "## What moves the result most",
    ] + [f"{s['assumption']}: NPV from {_money(s['npv_low'])} to {_money(s['npv_high'])} "
         f"(value {s['low']:g} to {s['high']:g})" for s in sens[:4]] + [
        "",
        "## Subdivide or sell whole",
    ] + [f"{s['id']} {s['name']}: NPV subdivided {_money(s['npv_subdivision'])} vs sold whole {_money(s['npv_whole'])}"
         for s in strat] + [
        "",
        "## Memos (AI-written, every number checked against the model)",
    ] + [f"{m['id']}: {m.get('recommendation', '-')} - {m.get('headline', m['status'])}"[:150] for m in memos]
    with PdfPages(path) as pdf:
        _text_page(pdf, "Land portfolio: cost x return", lines)
        for fig in (fig_cash(pf), fig_parcels(pf), fig_scenarios(scen), fig_tornado(sens)):
            pdf.savefig(fig)
            plt.close(fig)
    return path


def dashboard(path: Path, pf, scen, sens, strat, memos) -> Path:
    data = {
        "kpis": {"VGV": _money(pf["vgv"]), "Net profit": _money(pf["profit"]), "Margin": _pct(pf["margin"]),
                 f"NPV at {config.base()['discount_rate_year']:.0%}": _money(pf["npv"]), "IRR": _pct(pf["irr"]),
                 "Max exposure": _money(pf["max_exposure"])},
        "months": [month_label(m) for m in pf["months"]], "net": [round(v) for v in pf["net"]],
        "cumulative": [round(v) for v in pf["cumulative"]],
        "parcels": [{"id": p["id"], "name": p["name"], "strategy": p["strategy"], "vgv": round(p["vgv"]),
                     "npv": round(p["npv"]), "irr": None if p["irr"] is None else round(p["irr"] * 100, 1),
                     "payback": p["payback_months"]} for p in pf["projects"]],
        "scenarios": [{"name": s["scenario"], "npv": round(s["npv"]), "irr": None if s["irr"] is None else round(s["irr"] * 100, 1)} for s in scen],
        "tornado": [{"name": s["assumption"], "low": round(s["npv_low"] - s["base_npv"]),
                     "high": round(s["npv_high"] - s["base_npv"])} for s in sens],
        "memos": [{"id": m["id"], "rec": m.get("recommendation", "-"), "headline": m.get("headline", m["status"]),
                   "thesis": m.get("thesis", "")} for m in memos],
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Land Portfolio Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{--bg:#f6f7f8;--card:#fff;--ink:#1d2b33;--muted:#5b6a72;--blue:#1f4e5f;--orange:#e07b39;--green:#3c8d5a;--red:#b8433a}
body{margin:0;font:14px/1.45 system-ui,Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--ink)}
main{max-width:1100px;margin:0 auto;padding:20px 16px}
h1{font-size:22px;margin:0 0 4px}.sub{color:var(--muted);margin:0 0 18px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.kpi{background:var(--card);border-radius:8px;padding:12px}.kpi b{display:block;font-size:20px;color:var(--blue)}
.kpi span{color:var(--muted);font-size:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
.card{background:var(--card);border-radius:8px;padding:14px;min-width:0}.card h2{font-size:15px;margin:0 0 8px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:5px 6px;border-bottom:1px solid #e3e7ea}
td.n{text-align:right;font-variant-numeric:tabular-nums}.rec{font-weight:600}
.wide{grid-column:1/-1}.scroll{overflow-x:auto}
</style></head><body><main>
<h1>Land portfolio: cost x return</h1>
<p class="sub">Synthetic data generated by generate_data.py. Model, assumptions and sources: see the repository.</p>
<div class="kpis" id="kpis"></div>
<div class="grid">
<div class="card wide"><h2>Cash flow: monthly net and cumulative</h2><canvas id="cash" height="110"></canvas></div>
<div class="card"><h2>NPV by parcel</h2><canvas id="npv" height="220"></canvas></div>
<div class="card"><h2>Scenarios: portfolio NPV</h2><canvas id="scen" height="220"></canvas></div>
<div class="card wide"><h2>Sensitivity: change in portfolio NPV</h2><canvas id="torn" height="90"></canvas></div>
<div class="card wide scroll"><h2>Parcels</h2><table id="ptab"></table></div>
<div class="card wide scroll"><h2>Investment memos (AI-written, numbers checked against the model)</h2><table id="mtab"></table></div>
</div></main>
<script>
const D=__DATA__;
const brl=v=>'R$ '+(v/1e6).toLocaleString('en-US',{maximumFractionDigits:1})+' mi';
document.getElementById('kpis').innerHTML=Object.entries(D.kpis).map(([k,v])=>`<div class="kpi"><b>${v}</b><span>${k}</span></div>`).join('');
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const mi={ticks:{callback:v=>(v/1e6).toFixed(1)}};
new Chart(cash,{data:{labels:D.months,datasets:[
 {type:'bar',label:'monthly net',data:D.net,backgroundColor:D.net.map(v=>v>=0?css('--green'):css('--red'))},
 {type:'line',label:'cumulative',data:D.cumulative,borderColor:css('--blue'),pointRadius:0,yAxisID:'y2'}]},
 options:{scales:{y:mi,y2:{...mi,position:'right',grid:{drawOnChartArea:false}}}}});
new Chart(npv,{type:'bar',data:{labels:D.parcels.map(p=>p.id),datasets:[{label:'NPV (R$ mi)',data:D.parcels.map(p=>p.npv),
 backgroundColor:D.parcels.map(p=>p.strategy==='subdivision'?css('--blue'):css('--orange'))}]},options:{indexAxis:'y',scales:{x:mi},plugins:{legend:{display:false}}}});
new Chart(scen,{type:'bar',data:{labels:D.scenarios.map(s=>s.name),datasets:[{label:'NPV',data:D.scenarios.map(s=>s.npv),
 backgroundColor:[css('--red'),css('--blue'),css('--green')]}]},options:{scales:{y:mi},plugins:{legend:{display:false}}}});
new Chart(torn,{type:'bar',data:{labels:D.tornado.map(t=>t.name),datasets:[
 {label:'at low value',data:D.tornado.map(t=>t.low),backgroundColor:css('--orange')},
 {label:'at high value',data:D.tornado.map(t=>t.high),backgroundColor:css('--blue')}]},
 options:{indexAxis:'y',scales:{x:{...mi,stacked:true},y:{stacked:true}}}});
ptab.innerHTML='<tr><th>Id</th><th>Parcel</th><th>Strategy</th><th>VGV</th><th>NPV</th><th>IRR</th><th>Payback</th></tr>'+
 D.parcels.map(p=>`<tr><td>${p.id}</td><td>${p.name}</td><td>${p.strategy}</td><td class="n">${brl(p.vgv)}</td><td class="n">${brl(p.npv)}</td><td class="n">${p.irr??'n/a'}%</td><td class="n">${p.payback??'-'} mo</td></tr>`).join('');
mtab.innerHTML='<tr><th>Id</th><th>Recommendation</th><th>Memo</th></tr>'+
 D.memos.map(m=>`<tr><td>${m.id}</td><td class="rec">${m.rec}</td><td><b>${m.headline}</b><br>${m.thesis}</td></tr>`).join('');
</script></body></html>
"""
