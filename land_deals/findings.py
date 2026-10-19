"""Plain-English conclusions computed from the results, shared by the workbook, the PDF and the dashboard, so the
three always say the same thing."""
from __future__ import annotations

from . import config

LABELS = {  # assumption -> (readable name, how to show its value)
    "lot_price_factor": ("Lot and land prices", lambda v: f"{v - 1:+.0%}"),
    "absorption_months": ("Months to sell all lots", lambda v: f"{v:.0f} months"),
    "infra_per_m2": ("Infrastructure cost", lambda v: f"R$ {v:.0f}/m2"),
    "discount_rate_year": ("Hurdle rate", lambda v: f"{v:.0%} a year"),
    "hold_months": ("Holding before a whole sale", lambda v: f"{v:.0f} months"),
    "cash_share": ("Share of sales paid in cash", lambda v: f"{v:.0%}"),
    "default_rate": ("Default on installments", lambda v: f"{v:.0%}"),
}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def when(m: int | None) -> str:
    if m is None:
        return "not reached"
    y, mo = config.START
    k = mo - 1 + m
    return f"{MONTHS[k % 12]} {y + k // 12}"


def mi(v: float) -> str:
    return f"R$ {v / 1e6:,.1f} million"


def pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1%}"


def label(name: str) -> str:
    return LABELS.get(name, (name, None))[0]


def value(name: str, v: float) -> str:
    fmt = LABELS.get(name, (None, lambda x: f"{x:g}"))[1]
    return fmt(v)


def conclusions(pf: dict, scen: list[dict], sens: list[dict], strat: list[dict]) -> list[str]:
    hurdle = config.base()["discount_rate_year"]
    subs = [p for p in pf["projects"] if p["strategy"] == "subdivision"]
    whole = [p for p in pf["projects"] if p["strategy"] == "whole"]
    out = []
    if subs:
        out.append(f"The {len(subs)} subdivisions carry the portfolio: NPV of {mi(sum(p['npv'] for p in subs))} "
                   f"against {mi(pf['npv'])} in total.")
    if whole:
        irrs = [p["irr"] for p in whole if p["irr"] is not None]
        below = sum(1 for x in irrs if x < hurdle)
        out.append(f"The {len(whole)} parcels sold whole return {pct(min(irrs))} to {pct(max(irrs))} a year; "
                   f"{below} of them are below the {hurdle:.0%} hurdle, because holding land costs maintenance "
                   f"and tax while it appreciates more slowly than the hurdle rate.")
    top = sens[0]
    out.append(f"{label(top['assumption'])} moves NPV the most: from {mi(top['npv_low'])} at "
               f"{value(top['assumption'], top['low'])} to {mi(top['npv_high'])} at {value(top['assumption'], top['high'])}.")
    out.append(f"Cash need peaks at {mi(pf['max_exposure'])} in {when(pf['exposure_month'])}; the portfolio pays "
               f"back in {when(pf['payback_month'])}, {pf['payback_month']} months after the first purchase.")
    by = {s["scenario"]: s for s in scen}
    if "pessimistic" in by:
        p = by["pessimistic"]
        out.append(f"In the pessimistic scenario NPV is {mi(p['npv'])} and IRR {pct(p['irr'])}; "
                   f"the optimistic one reaches {mi(by['optimistic']['npv'])}.")
    if strat:
        wins = sum(1 for s in strat if s["npv_subdivision"] > s["npv_whole"])
        out.append(f"Subdividing beats selling whole in {wins} of the {len(strat)} urban parcels where both are possible.")
    return out
