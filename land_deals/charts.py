"""Static outputs: the PDF report (matplotlib) and the HTML dashboard (Chart.js, no build step).
The PDF and the dashboard draw the same charts from the same numbers, including the conclusions in findings.py."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.ticker import FuncFormatter

from . import config
from .findings import conclusions, label, value, when
from .workbook import month_label

BLUE, ORANGE, GREY, GREEN, RED, INK = "#1f4e5f", "#e07b39", "#9aa5ab", "#3c8d5a", "#b8433a", "#1d2b33"
MI = FuncFormatter(lambda v, _: f"{v:,.1f}")
A4 = (11.69, 8.27)  # landscape
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})


def _money(v):
    return f"R$ {v / 1e6:,.1f} mi"


def _money_k(v):
    """R$ thousands below one million, so small parcel values do not round to 0.1."""
    return _money(v) if abs(v) >= 1e6 else f"R$ {v / 1e3:,.0f} k"


def _tex(s: str) -> str:
    """matplotlib reads $...$ as math; escape the currency sign."""
    return s.replace("$", r"\$")


def _pct(v):
    return "n/a" if v is None else f"{v:.1%}"


def _quarters(pf) -> tuple[list[str], list[float], list[float]]:
    """Monthly portfolio flows grouped by quarter, in R$ million: labels, net per quarter, cumulative at quarter end."""
    labels, net, cum = [], [], []
    for m, v, c in zip(pf["months"], pf["net"], pf["cumulative"]):
        lab = month_label(m)
        q = f"{lab[:4]} Q{(int(lab[5:]) - 1) // 3 + 1}"
        if not labels or labels[-1] != q:
            labels.append(q)
            net.append(0.0)
            cum.append(0.0)
        net[-1] += v / 1e6
        cum[-1] = c / 1e6
    return labels, [round(x, 2) for x in net], [round(x, 2) for x in cum]


# ------------------------------------------------------------------------------------------- charts
def fig_cash(pf, figsize=(11, 4.6)):
    labels, net, cum = _quarters(pf)
    fig, ax = plt.subplots(figsize=figsize)
    x = range(len(labels))
    ax.bar(x, net, color=[GREEN if v >= 0 else RED for v in net], width=0.75, label="net cash in the quarter")
    ax.plot(x, cum, color=BLUE, lw=2.4, label="cumulative cash")
    low = cum.index(min(cum))
    ax.scatter([low], [cum[low]], color=BLUE, zorder=3, s=40)
    ax.annotate(
        _tex(f"maximum exposure {_money(pf['max_exposure'])} ({when(pf['exposure_month'])})"),
        (low, cum[low]),
        xytext=(10, -4),
        textcoords="offset points",
        fontsize=9,
        color=BLUE,
        va="top",
    )
    ax.axhline(0, color=GREY, lw=0.8)
    ax.set_xticks(list(x)[::4], labels[::4], fontsize=8)
    ax.yaxis.set_major_formatter(MI)
    ax.set_ylabel(_tex("R$ million"))
    ax.set_title("Portfolio cash flow by quarter", loc="left", fontsize=12, weight="bold")
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout()
    return fig


def fig_parcels(pf, figsize=(11, 4.6)):
    ps = pf["projects"]
    hurdle = config.base()["discount_rate_year"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=figsize, sharey=True)
    names = [f"{p['id']} {p['name']}" for p in ps]
    npv = [p["npv"] / 1e6 for p in ps]
    a1.barh(names, npv, color=[BLUE if p["strategy"] == "subdivision" else ORANGE for p in ps])
    for y, v in enumerate(npv):
        a1.annotate(
            f"{v:,.1f}",
            (v, y),
            xytext=(3 if v >= 0 else -3, 0),
            textcoords="offset points",
            ha="left" if v >= 0 else "right",
            va="center",
            fontsize=8,
        )
    a1.axvline(0, color=GREY, lw=0.8)
    a1.xaxis.set_major_formatter(MI)
    a1.set_xlabel(_tex("NPV, R$ million"))
    a1.set_xlim(min(npv + [0]) * 1.35 - 0.1, max(npv) * 1.2)
    a1.set_title("NPV by parcel (blue: subdivided, orange: sold whole)", loc="left", fontsize=11, weight="bold")
    a1.invert_yaxis()
    irr = [(p["irr"] or 0) * 100 for p in ps]
    a2.barh(names, irr, color=[GREEN if v >= hurdle * 100 else RED for v in irr])
    for y, v in enumerate(irr):
        a2.annotate(f"{v:.1f}%", (v, y), xytext=(3, 0), textcoords="offset points", va="center", fontsize=8)
    a2.axvline(hurdle * 100, color=GREY, ls="--", lw=1)
    a2.set_xlabel("IRR, % per year")
    a2.set_xlim(0, max(irr) * 1.2)
    a2.set_title(f"IRR per year vs the {hurdle:.0%} hurdle (dashed)", loc="left", fontsize=11, weight="bold")
    fig.tight_layout()
    return fig


def fig_scenarios_tornado(scen, sens, figsize=(11, 4.6)):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=figsize, gridspec_kw={"width_ratios": [1, 1.6]})
    names = [s["scenario"] for s in scen]
    vals = [s["npv"] / 1e6 for s in scen]
    a1.bar(names, vals, color=[RED, BLUE, GREEN])
    for i, s in enumerate(scen):
        a1.annotate(
            f"{vals[i]:,.1f}\nIRR {_pct(s['irr'])}",
            (i, vals[i]),
            ha="center",
            va="bottom" if vals[i] >= 0 else "top",
            xytext=(0, 3 if vals[i] >= 0 else -3),
            textcoords="offset points",
            fontsize=8,
        )
    a1.axhline(0, color=GREY, lw=0.8)
    a1.set_ylim(min(vals + [0]) * 1.3, max(vals) * 1.3)
    a1.yaxis.set_major_formatter(MI)
    a1.set_ylabel(_tex("NPV, R$ million"))
    a1.set_title("Portfolio NPV by scenario", loc="left", fontsize=11, weight="bold")
    base = sens[0]["base_npv"]
    labels = [label(s["assumption"]) for s in sens][::-1]
    lows = [(s["npv_low"] - base) / 1e6 for s in sens][::-1]
    highs = [(s["npv_high"] - base) / 1e6 for s in sens][::-1]
    a2.barh(labels, lows, color=ORANGE, label="assumption at its low value")
    a2.barh(labels, highs, color=BLUE, label="assumption at its high value")
    a2.axvline(0, color=GREY, lw=0.8)
    a2.xaxis.set_major_formatter(MI)
    a2.set_xlabel(_tex(f"change in NPV vs base {_money(base)}, R$ million"))
    a2.set_title("Sensitivity: one assumption at a time", loc="left", fontsize=11, weight="bold")
    a2.legend(fontsize=8, frameon=False, loc="lower right")
    fig.tight_layout()
    return fig


# ------------------------------------------------------------------------------------------- PDF
def _page(pdf, title: str, subtitle: str = ""):
    fig = plt.figure(figsize=A4)
    fig.text(0.05, 0.95, title, fontsize=16, weight="bold", color=BLUE, va="top")
    if subtitle:
        fig.text(0.05, 0.905, subtitle, fontsize=9, color=GREY, va="top", parse_math=False)
    return fig


def _table(fig, rect, header, rows, col_widths=None, align=None, font=8.5):
    ax = fig.add_axes(rect)
    ax.axis("off")
    t = ax.table(cellText=rows, colLabels=header, loc="upper left", cellLoc="left", colWidths=col_widths)
    t.auto_set_font_size(False)
    t.set_fontsize(font)
    t.scale(1, 1.35)
    for (r, c), cell in t.get_celld().items():
        cell.set_edgecolor("#e3e7ea")
        cell.get_text().set_parse_math(False)
        if r == 0:
            cell.set_facecolor(BLUE)
            cell.get_text().set_color("white")
            cell.get_text().set_weight("bold")
        if align and align[c] == "r":
            cell.get_text().set_horizontalalignment("right")
    return ax


def _bullets(fig, x, y, items, width=150, size=9.5, step=0.032):
    for it in items:
        lines = textwrap.wrap(it, width)
        for j, line in enumerate(lines):
            fig.text(x, y, ("•  " if j == 0 else "    ") + line, fontsize=size, va="top", color=INK, parse_math=False)
            y -= step * 0.72
        y -= step * 0.35
    return y


def pdf_report(path: Path, pf, scen, sens, strat, memos) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    a = config.base()
    hurdle = a["discount_rate_year"]
    rec = {m["id"]: m.get("recommendation", "-") for m in memos}
    sub = "Synthetic data generated by generate_data.py. Every number is computed by the model in this repository."
    with PdfPages(path, metadata={"CreationDate": None}) as pdf:  # no timestamp: same input, same file
        # 1. executive summary
        fig = _page(pdf, "Land portfolio: cost x return - executive summary", sub)
        kpis = [
            ["Parcels", f"{len(pf['projects'])}"],
            ["VGV (total sales value)", _money(pf["vgv"])],
            [
                "  subdivided / sold whole",
                f"{_money(pf['vgv_by_strategy']['subdivision'])} / {_money(pf['vgv_by_strategy']['whole'])}",
            ],
            ["Net profit (nominal)", _money(pf["profit"])],
            ["Margin on VGV", _pct(pf["margin"])],
            [f"NPV at {hurdle:.0%} a year", _money(pf["npv"])],
            ["IRR per year", _pct(pf["irr"])],
            ["Maximum cash exposure", f"{_money(pf['max_exposure'])} ({when(pf['exposure_month'])})"],
            ["Payback", when(pf["payback_month"])],
        ]
        _table(fig, [0.05, 0.42, 0.38, 0.44], ["Portfolio", "Base case"], kpis, [0.55, 0.45], "lr", font=9)
        _table(
            fig,
            [0.48, 0.62, 0.47, 0.24],
            ["Scenario", "VGV", "NPV", "IRR", "Max exposure"],
            [
                [s["scenario"], _money(s["vgv"]), _money(s["npv"]), _pct(s["irr"]), _money(s["max_exposure"])]
                for s in scen
            ],
            [0.22, 0.2, 0.2, 0.14, 0.24],
            "lrrrr",
            font=9,
        )
        fig.text(
            0.48,
            0.735,
            "Pessimistic and optimistic move lot prices, sales speed, infrastructure cost, holding "
            "time, appreciation and default to the ends of their ranges.",
            fontsize=8,
            color=GREY,
            va="top",
            wrap=True,
            parse_math=False,
        )
        labels, _, cum = _quarters(pf)
        ax = fig.add_axes([0.53, 0.43, 0.42, 0.2])
        ax.plot(range(len(cum)), cum, color=BLUE, lw=2)
        ax.axhline(0, color=GREY, lw=0.8)
        ax.set_xticks(range(len(labels))[::8], [lab[:4] for lab in labels[::8]], fontsize=7)
        ax.tick_params(labelsize=7)
        ax.set_title(_tex("Cumulative cash, R$ million (detail on the next page)"), fontsize=8, loc="left")
        counts = {}
        for r in rec.values():
            counts[r] = counts.get(r, 0) + 1
        fig.text(0.05, 0.37, "What the numbers say", fontsize=12, weight="bold", color=BLUE, va="top")
        items = conclusions(pf, scen, sens, strat) + [
            "AI memos (numbers checked against the model): "
            + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in sorted(counts.items()))
            + "."
        ]
        _bullets(fig, 0.05, 0.33, items)
        pdf.savefig(fig)
        plt.close(fig)
        # 2. cash flow
        fig = fig_cash(pf, figsize=A4)
        pdf.savefig(fig)
        plt.close(fig)
        # 3. parcels table
        fig = _page(pdf, "Parcels", f"Hurdle rate {hurdle:.0%} a year. Payback in months after purchase.")
        rows = []
        for p in pf["projects"]:
            rows.append(
                [
                    p["id"],
                    p["name"],
                    p["kind"],
                    f"{p['area_m2']:,.0f}",
                    p["strategy"],
                    _money_k(-p["totals"]["acquisition"]),
                    _money_k(p["vgv"]),
                    _money_k(p["npv"]),
                    _pct(p["irr"]),
                    _money_k(p["max_exposure"]),
                    "-" if p["payback_months"] is None else str(p["payback_months"]),
                    rec.get(p["id"], "-").replace("_", " "),
                ]
            )
        _table(
            fig,
            [0.03, 0.5, 0.94, 0.35],
            [
                "Id",
                "Parcel",
                "Kind",
                "Area m2",
                "Strategy",
                "Price",
                "VGV",
                "NPV",
                "IRR",
                "Max exposure",
                "Payback",
                "AI memo",
            ],
            rows,
            [0.04, 0.17, 0.065, 0.065, 0.08, 0.08, 0.08, 0.08, 0.055, 0.09, 0.06, 0.135],
            "lllrlrrrrrrl",
            font=8,
        )
        fig.text(
            0.03,
            0.42,
            "Subdivide or sell whole (urban parcels where both are possible)",
            fontsize=11,
            weight="bold",
            color=BLUE,
            va="top",
        )
        _table(
            fig,
            [0.03, 0.12, 0.7, 0.28],
            ["Id", "Parcel", "Area m2", "Rule picks", "NPV subdivided", "IRR", "NPV sold whole", "IRR"],
            [
                [
                    s["id"],
                    s["name"],
                    f"{s['area_m2']:,.0f}",
                    s["rule"],
                    _money_k(s["npv_subdivision"]),
                    _pct(s["irr_subdivision"]),
                    _money_k(s["npv_whole"]),
                    _pct(s["irr_whole"]),
                ]
                for s in strat
            ],
            [0.06, 0.22, 0.1, 0.12, 0.15, 0.08, 0.15, 0.08],
            "llrlrrrr",
            font=8,
        )
        pdf.savefig(fig)
        plt.close(fig)
        # 4-5. charts
        for fig in (fig_parcels(pf, figsize=A4), fig_scenarios_tornado(scen, sens, figsize=A4)):
            pdf.savefig(fig)
            plt.close(fig)
        # 6. key assumptions
        fig = _page(
            pdf,
            "Key assumptions",
            "Base value and the range used in scenarios and sensitivity. "
            "'illustrative' = typical value, not market research. Full list: sheet Assumptions.",
        )
        keys = [
            "infra_per_m2",
            "lot_size_m2",
            "saleable_ratio",
            "approval_months",
            "absorption_months",
            "itbi_rate",
            "deed_registry_rate",
            "iptu_rate",
            "itr_rate",
            "sales_tax_rate",
            "broker_rate",
            "installments",
            "monthly_interest",
            "index_rate_year",
            "default_rate",
            "discount_rate_year",
        ]
        rows = [
            [
                k,
                f"{config.ASSUMPTIONS[k][0]:g}",
                f"{config.ASSUMPTIONS[k][1]:g} - {config.ASSUMPTIONS[k][2]:g}",
                config.ASSUMPTIONS[k][3],
                textwrap.shorten(config.ASSUMPTIONS[k][4], 95),
            ]
            for k in keys
        ]
        _table(
            fig,
            [0.03, 0.1, 0.94, 0.76],
            ["Assumption", "Base", "Range", "Unit", "Source"],
            rows,
            [0.14, 0.06, 0.1, 0.17, 0.53],
            "lrrll",
            font=7.5,
        )
        pdf.savefig(fig)
        plt.close(fig)
        # 7+. memos
        checked = [m for m in memos if m.get("headline")]
        for start in range(0, len(checked), 3):
            fig = _page(
                pdf,
                "Investment memos",
                "Written by Claude from the model's facts; every number was checked "
                "against those facts before the memo was kept.",
            )
            y = 0.85
            for m in checked[start : start + 3]:
                fig.text(
                    0.05,
                    y,
                    _tex(f"{m['facts']['parcel']} - {m['recommendation'].replace('_', ' ')}"),
                    fontsize=11,
                    weight="bold",
                    color=BLUE,
                    va="top",
                )
                y = (
                    _bullets(
                        fig,
                        0.05,
                        y - 0.035,
                        [m["headline"], m["thesis"]]
                        + [f"Risk: {r}" for r in m["risks"]]
                        + [f"Condition: {c}" for c in m["conditions"]],
                        width=165,
                        size=8.5,
                        step=0.03,
                    )
                    - 0.02
                )
            pdf.savefig(fig)
            plt.close(fig)
    return path


def dashboard(path: Path, pf, scen, sens, strat, memos) -> Path:
    quarters, q_net, q_cum = _quarters(pf)
    mi = lambda v: round(v / 1e6, 2)
    data = {
        "kpis": {
            "VGV": _money(pf["vgv"]),
            "Net profit": _money(pf["profit"]),
            "Margin": _pct(pf["margin"]),
            f"NPV at {config.base()['discount_rate_year']:.0%}": _money(pf["npv"]),
            "IRR": _pct(pf["irr"]),
            "Max exposure": _money(pf["max_exposure"]),
        },
        "quarters": quarters,
        "q_net": q_net,
        "q_cum": q_cum,
        "exposure": {"value": mi(-pf["max_exposure"]), "month": when(pf["exposure_month"])},
        "findings": conclusions(pf, scen, sens, strat),
        "parcels": [
            {
                "id": p["id"],
                "name": p["name"],
                "strategy": p["strategy"],
                "vgv": mi(p["vgv"]),
                "npv": mi(p["npv"]),
                "irr": None if p["irr"] is None else round(p["irr"] * 100, 1),
                "payback": p["payback_months"],
                "rec": next((m.get("recommendation") for m in memos if m["id"] == p["id"]), None) or "-",
            }
            for p in pf["projects"]
        ],
        "scenarios": [
            {"name": s["scenario"], "npv": mi(s["npv"]), "irr": None if s["irr"] is None else round(s["irr"] * 100, 1)}
            for s in scen
        ],
        "tornado": [
            {
                "name": f"{label(s['assumption'])} ({value(s['assumption'], s['low'])} to "
                f"{value(s['assumption'], s['high'])})",
                "low": mi(s["npv_low"] - s["base_npv"]),
                "high": mi(s["npv_high"] - s["base_npv"]),
            }
            for s in sens
        ],
        "memos": [
            {
                "id": m["id"],
                "rec": m.get("recommendation", "-"),
                "headline": m.get("headline", m["status"]),
                "thesis": m.get("thesis", ""),
            }
            for m in memos
        ],
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8", newline="\n")
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
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr));gap:14px}
.card{background:var(--card);border-radius:8px;padding:14px;min-width:0}.card h2{font-size:15px;margin:0 0 2px}
.note{color:var(--muted);font-size:12px;margin:0 0 8px}
.box{position:relative;height:300px}.box.tall{height:360px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:5px 6px;border-bottom:1px solid #e3e7ea}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.rec{font-weight:600}
.wide{grid-column:1/-1}ul{margin:6px 0 0;padding-left:18px}li{margin:3px 0}.scroll{overflow-x:auto}
</style></head><body><main>
<h1>Land portfolio: cost x return</h1>
<p class="sub">Synthetic data generated by generate_data.py.
<a href="https://github.com/gcabralcavalcanti/land-deals-automation/blob/main/final-report.pdf">Full report (PDF)</a> ·
<a href="https://github.com/gcabralcavalcanti/land-deals-automation">Code, model and assumptions</a></p>
<div class="kpis" id="kpis"></div>
<div class="card wide" style="margin-bottom:14px"><h2>What the numbers say</h2><ul id="find"></ul></div>
<div class="grid">
<div class="card wide"><h2>Cash flow by quarter (R$ million)</h2>
<p class="note">Bars: net cash of each quarter. Line: cumulative cash, with the maximum exposure marked.</p>
<div class="box"><canvas id="cash"></canvas></div></div>
<div class="card"><h2>NPV by parcel (R$ million)</h2><p class="note">Blue: subdivided. Orange: sold whole.</p>
<div class="box tall"><canvas id="npv"></canvas></div></div>
<div class="card"><h2>Portfolio NPV by scenario (R$ million)</h2><p class="note">Label: NPV and IRR per year.</p>
<div class="box tall"><canvas id="scen"></canvas></div></div>
<div class="card wide"><h2>Sensitivity: change in portfolio NPV (R$ million)</h2>
<p class="note">Each assumption moves alone from its low to its high value.</p>
<div class="box"><canvas id="torn"></canvas></div></div>
<div class="card wide scroll"><h2>Parcels</h2><table id="ptab"></table></div>
<div class="card wide scroll"><h2>Investment memos (AI-written, numbers checked against the model)</h2><table id="mtab"></table></div>
</div></main>
<script>
const D=__DATA__;
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmt=v=>v.toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1});
const axis=title=>({beginAtZero:true,title:{display:true,text:title},ticks:{callback:v=>fmt(v)}});
const valueLabels={id:'valueLabels',afterDatasetsDraw(c,_,o){if(!o.text)return;const x=c.ctx;x.save();
 x.font='12px system-ui,Arial';x.fillStyle=css('--ink');const h=c.options.indexAxis==='y';
 c.getDatasetMeta(0).data.forEach((el,i)=>{const t=o.text(i);if(!t)return;const v=c.data.datasets[0].data[i];
  x.textAlign=h?(v<0?'right':'left'):'center';x.textBaseline=h?'middle':(v<0?'top':'bottom');
  x.fillText(t,h?el.x+(v<0?-4:4):el.x,h?el.y:el.y+(v<0?4:-4));});x.restore();}};
Chart.register(valueLabels);
const opts=extra=>({responsive:true,maintainAspectRatio:false,...extra});
document.getElementById('find').innerHTML=D.findings.map(f=>`<li>${f}</li>`).join('');
document.getElementById('kpis').innerHTML=Object.entries(D.kpis).map(([k,v])=>`<div class="kpi"><b>${v}</b><span>${k}</span></div>`).join('');
const ex=D.q_cum.indexOf(Math.min(...D.q_cum));
new Chart(document.getElementById('cash'),{data:{labels:D.quarters,datasets:[
 {type:'bar',label:'net cash in the quarter',data:D.q_net,backgroundColor:D.q_net.map(v=>v>=0?css('--green'):css('--red')),order:2},
 {type:'line',label:'cumulative cash',data:D.q_cum,borderColor:css('--blue'),borderWidth:2.5,order:1,
  pointRadius:D.q_cum.map((_,i)=>i===ex?6:0),pointBackgroundColor:css('--blue')}]},
 options:opts({scales:{y:axis('R$ million'),x:{ticks:{maxRotation:0,autoSkip:true,maxTicksLimit:10}}},
  plugins:{tooltip:{callbacks:{label:c=>`${c.dataset.label}: R$ ${fmt(c.parsed.y)} mi`}},
   subtitle:{display:true,text:`Maximum exposure: R$ ${fmt(-D.exposure.value)} mi (${D.exposure.month})`,color:css('--blue')}}})});
new Chart(document.getElementById('npv'),{type:'bar',data:{labels:D.parcels.map(p=>`${p.id} ${p.name}`),
 datasets:[{label:'NPV',data:D.parcels.map(p=>p.npv),backgroundColor:D.parcels.map(p=>p.strategy==='subdivision'?css('--blue'):css('--orange'))}]},
 options:opts({indexAxis:'y',layout:{padding:{right:36,left:4}},scales:{x:{...axis('R$ million'),grace:'10%'},y:{ticks:{font:{size:11},callback:(v,i)=>{const t=`${D.parcels[i].id} ${D.parcels[i].name}`;return t.length>22?t.slice(0,21)+'…':t;}}}},
  plugins:{legend:{display:false},valueLabels:{text:i=>fmt(D.parcels[i].npv)}}})});
new Chart(document.getElementById('scen'),{type:'bar',data:{labels:D.scenarios.map(s=>s.name),
 datasets:[{label:'NPV',data:D.scenarios.map(s=>s.npv),backgroundColor:[css('--red'),css('--blue'),css('--green')]}]},
 options:opts({layout:{padding:{top:22,bottom:4,left:8,right:8}},scales:{y:{...axis('R$ million'),grace:'15%'}},
  plugins:{legend:{display:false},valueLabels:{text:i=>`${fmt(D.scenarios[i].npv)} | IRR ${D.scenarios[i].irr}%`}}})});
new Chart(document.getElementById('torn'),{type:'bar',data:{labels:D.tornado.map(t=>t.name),datasets:[
 {label:'assumption at its low value',data:D.tornado.map(t=>t.low),backgroundColor:css('--orange')},
 {label:'assumption at its high value',data:D.tornado.map(t=>t.high),backgroundColor:css('--blue')}]},
 options:opts({indexAxis:'y',scales:{x:{...axis('change in NPV, R$ million'),stacked:true},y:{stacked:true}}})});
const brl=v=>'R$ '+fmt(v)+' mi';
document.getElementById('ptab').innerHTML='<tr><th>Id</th><th>Parcel</th><th>Strategy</th><th>VGV</th><th>NPV</th><th>IRR</th><th>Payback</th><th>AI memo</th></tr>'+
 D.parcels.map(p=>`<tr><td>${p.id}</td><td>${p.name}</td><td>${p.strategy}</td><td class="n">${brl(p.vgv)}</td><td class="n">${brl(p.npv)}</td><td class="n">${p.irr??'n/a'}%</td><td class="n">${p.payback??'-'} mo</td><td>${p.rec.replace(/_/g,' ')}</td></tr>`).join('');
document.getElementById('mtab').innerHTML='<tr><th>Id</th><th>Recommendation</th><th>Memo</th></tr>'+
 D.memos.map(m=>`<tr><td>${m.id}</td><td class="rec">${m.rec.replace(/_/g,' ')}</td><td><b>${m.headline}</b><br>${m.thesis}</td></tr>`).join('');
</script></body></html>
"""
