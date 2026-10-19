"""Cost x return model of a land parcel, month by month, and of the whole portfolio.

Two strategies: subdivide (loteamento: approval, infrastructure, sell lots over an absorption period) or resell the
parcel whole after a holding period. Sales are part cash, part financed (down payment + Price-table installments
corrected yearly by a fixed index).
"""

from __future__ import annotations

import math
from collections import defaultdict

from . import config
from .text import pmt

INFLOWS = ("cash_sales", "down_payments", "installments")
OUTFLOWS = (
    "acquisition",
    "acquisition_taxes",
    "studies_approval",
    "infrastructure",
    "small_constructions",
    "marketing",
    "maintenance",
    "property_tax",
    "broker",
    "sales_tax",
)
CATEGORIES = OUTFLOWS + INFLOWS


def strategy_for(parcel: dict, a: dict) -> str:
    if parcel.get("strategy"):
        return parcel["strategy"]
    big = parcel["area_m2"] >= a["subdivision_min_m2"]
    return "subdivision" if big and parcel["kind"] in ("urban", "expansion") and parcel.get("lot_price_m2") else "whole"


def _receive(flows, month: int, amount: float, a: dict, n: int, rate: float, index_year: float) -> None:
    """A sale of `amount` signed in `month`, financed: down payment now, installments from the next month."""
    down = amount * a["down_rate"] if n else amount
    flows["down_payments"][month] += down
    balance = amount - down
    if balance <= 0 or n <= 0:
        return
    inst = pmt(balance, rate, n)
    for k in range(1, n + 1):
        flows["installments"][month + k] += inst * (1 + index_year) ** ((k - 1) // 12) * (1 - a["default_rate"])


def project(parcel: dict, assumptions: dict | None = None, strategy: str | None = None) -> dict:
    a = {**config.base(), **(assumptions or {}), **parcel.get("overrides", {})}
    strategy = strategy or strategy_for(parcel, a)
    t0, area, price = parcel["acquisition_month"], parcel["area_m2"], parcel["acquisition_price"]
    flows: dict[str, defaultdict] = {c: defaultdict(float) for c in CATEGORIES}
    flows["acquisition"][t0] -= price
    flows["acquisition_taxes"][t0] -= price * (a["itbi_rate"] + a["deed_registry_rate"])
    if parcel["kind"] == "rural":
        flows["acquisition_taxes"][t0] -= a["car_service"]
    tax_rate = a["itr_rate"] if parcel["kind"] == "rural" else a["iptu_rate"]
    maintenance = a["rural_maintenance_per_m2_month"] if parcel["kind"] == "rural" else a["maintenance_per_m2_month"]
    unsold: dict[int, float] = {}  # share of the area still owned, by month
    info: dict = {"strategy": strategy}

    if strategy == "subdivision":
        lot_size = a["lot_size_m2"]
        n_lots = math.floor(area * a["saleable_ratio"] / lot_size)
        lot_price = parcel["lot_price_m2"] * a["lot_price_factor"] * lot_size
        vgv = n_lots * lot_price
        approval, infra_m, absorb = int(a["approval_months"]), int(a["infra_months"]), int(a["absorption_months"])
        for m in range(approval):
            flows["studies_approval"][t0 + m] -= (a["topography_per_m2"] + a["approval_per_m2"]) * area / approval
        infra = a["infra_per_m2"] * n_lots * lot_size * (1 + a["labor_rate"])
        launch = t0 + approval
        for m in range(infra_m):
            flows["infrastructure"][launch + m] -= infra / infra_m
        flows["small_constructions"][t0 + 1] -= 4 * math.sqrt(area) * a["fence_per_m"]
        flows["small_constructions"][launch] -= a["gatehouse"]
        sold = 0.0
        for m in range(absorb):
            month = launch + m
            sales = vgv / absorb
            flows["marketing"][month] -= vgv * a["marketing_rate"] / absorb
            flows["broker"][month] -= sales * a["broker_rate"]
            flows["cash_sales"][month] += sales * a["cash_share"]
            _receive(
                flows,
                month,
                sales * (1 - a["cash_share"]),
                a,
                int(a["installments"]),
                a["monthly_interest"],
                a["index_rate_year"],
            )
            sold += 1 / absorb
            unsold[month] = max(0.0, 1 - sold)
        for m in range(t0, launch):
            unsold[m] = 1.0
        sell_out = launch + absorb - 1
        info.update(lots=n_lots, lot_price=lot_price, launch=launch, sell_out=sell_out, infra_total=infra)
    else:
        hold = int(a["hold_months"])
        sale_month = t0 + hold
        vgv = area * parcel["raw_price_m2"] * a["lot_price_factor"] * (1 + a["land_appreciation_year"]) ** (hold / 12)
        flows["broker"][sale_month] -= vgv * a["broker_rate"]
        whole = {**a, "down_rate": a["whole_down_rate"]}
        _receive(flows, sale_month, vgv, whole, int(a["whole_installments"]), a["monthly_interest"], 0.0)
        for m in range(t0, sale_month):
            unsold[m] = 1.0
        unsold[sale_month] = 0.0
        sell_out = sale_month
        info.update(lots=1, lot_price=vgv, launch=sale_month, sell_out=sale_month, infra_total=0.0)

    for m, share in unsold.items():
        flows["maintenance"][m] -= maintenance * area * share
        flows["property_tax"][m] -= tax_rate / 12 * price * share
    receipts = {m: sum(flows[c][m] for c in INFLOWS) for m in set().union(*(flows[c] for c in INFLOWS))}
    for m, r in receipts.items():
        flows["sales_tax"][m] -= r * a["sales_tax_rate"]

    last = max(m for c in CATEGORIES for m, v in flows[c].items() if abs(v) > 1e-9)
    months = list(range(t0, last + 1))
    net = [sum(flows[c].get(m, 0.0) for c in CATEGORIES) for m in months]
    res = {
        "id": parcel["id"],
        "name": parcel["name"],
        "kind": parcel["kind"],
        "area_m2": area,
        "vgv": vgv,
        "start": t0,
        "months": months,
        "net": net,
        "by_category": {c: {m: v for m, v in flows[c].items() if abs(v) > 1e-9} for c in CATEGORIES},
        **info,
    }
    res.update(metrics(months, net, a["discount_rate_year"], t0))
    res["totals"] = {c: sum(flows[c].values()) for c in CATEGORIES}
    res["margin"] = res["profit"] / vgv if vgv else None
    return res


# ------------------------------------------------------------------------------------------- metrics
def monthly_rate(year_rate: float) -> float:
    return (1 + year_rate) ** (1 / 12) - 1


def npv(net: list[float], year_rate: float) -> float:
    r = monthly_rate(year_rate)
    return sum(v / (1 + r) ** k for k, v in enumerate(net))


def irr(net: list[float]) -> float | None:
    """Annual IRR from monthly flows, by bisection. None when the flows never change sign."""
    if not (any(v < 0 for v in net) and any(v > 0 for v in net)):
        return None
    f = lambda r: sum(v / (1 + r) ** k for k, v in enumerate(net))
    lo, hi = -0.99, 1.0
    if f(lo) * f(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (1 + (lo + hi) / 2) ** 12 - 1


def metrics(months: list[int], net: list[float], discount_year: float, t0: int) -> dict:
    cum, running = [], 0.0
    for v in net:
        running += v
        cum.append(running)
    low = min(cum)
    trough = cum.index(low)
    payback = next((months[i] for i in range(trough, len(cum)) if cum[i] >= 0), None)
    profit = cum[-1]
    exposure = -low if low < 0 else 0.0
    duration = len(months)
    roi = profit / exposure if exposure else None
    return {
        "profit": profit,
        "npv": npv(net, discount_year),
        "irr": irr(net),
        "max_exposure": exposure,
        "exposure_month": months[trough],
        "payback_month": payback,
        "payback_months": payback - t0 if payback is not None else None,
        "duration_months": duration,
        "roi": roi,
        "roi_year": (1 + roi) ** (12 / duration) - 1 if roi is not None and roi > -1 else None,
        "cumulative": cum,
    }


def portfolio(parcels: list[dict], assumptions: dict | None = None) -> dict:
    a = {**config.base(), **(assumptions or {})}
    projects = [project(p, a) for p in parcels]
    by_month: dict[int, float] = defaultdict(float)
    by_cat: dict[str, dict[int, float]] = {c: defaultdict(float) for c in CATEGORIES}
    for pr in projects:
        for m, v in zip(pr["months"], pr["net"]):
            by_month[m] += v
        for c in CATEGORIES:
            for m, v in pr["by_category"][c].items():
                by_cat[c][m] += v
    months = list(range(max(by_month) + 1))
    net = [by_month.get(m, 0.0) for m in months]
    res = {
        "projects": projects,
        "months": months,
        "net": net,
        "by_category": {c: [by_cat[c].get(m, 0.0) for m in months] for c in CATEGORIES},
        "vgv": sum(p["vgv"] for p in projects),
        "vgv_by_strategy": {s: sum(p["vgv"] for p in projects if p["strategy"] == s) for s in ("subdivision", "whole")},
    }
    res.update(metrics(months, net, a["discount_rate_year"], 0))
    res["margin"] = res["profit"] / res["vgv"] if res["vgv"] else None
    return res


# ------------------------------------------------------------------------------------- what-ifs
SCENARIOS = {
    "pessimistic": {
        "lot_price_factor": "low",
        "absorption_months": "high",
        "infra_per_m2": "high",
        "hold_months": "high",
        "land_appreciation_year": "low",
        "default_rate": "high",
    },
    "base": {},
    "optimistic": {
        "lot_price_factor": "high",
        "absorption_months": "low",
        "infra_per_m2": "low",
        "hold_months": "low",
        "land_appreciation_year": "high",
        "default_rate": "low",
    },
}
SENSITIVITY = [
    "lot_price_factor",
    "absorption_months",
    "infra_per_m2",
    "discount_rate_year",
    "hold_months",
    "cash_share",
    "default_rate",
]


def _value(name: str, which: str) -> float:
    base_v, low, high = config.ASSUMPTIONS[name][:3]
    return {"low": low, "high": high, "base": base_v}[which]


def scenarios(parcels: list[dict]) -> list[dict]:
    out = []
    for name, levers in SCENARIOS.items():
        overrides = {k: _value(k, w) for k, w in levers.items()}
        pf = portfolio(parcels, overrides)
        out.append(
            {
                "scenario": name,
                "overrides": overrides,
                "vgv": pf["vgv"],
                "profit": pf["profit"],
                "npv": pf["npv"],
                "irr": pf["irr"],
                "max_exposure": pf["max_exposure"],
                "payback_month": pf["payback_month"],
                "margin": pf["margin"],
            }
        )
    return out


def sensitivity(parcels: list[dict]) -> list[dict]:
    base_npv = portfolio(parcels)["npv"]
    rows = []
    for name in SENSITIVITY:
        lo, hi = _value(name, "low"), _value(name, "high")
        npv_lo, npv_hi = portfolio(parcels, {name: lo})["npv"], portfolio(parcels, {name: hi})["npv"]
        rows.append(
            {
                "assumption": name,
                "low": lo,
                "high": hi,
                "npv_low": npv_lo,
                "npv_high": npv_hi,
                "base_npv": base_npv,
                "swing": abs(npv_hi - npv_lo),
            }
        )
    return sorted(rows, key=lambda r: -r["swing"])


def strategy_comparison(parcels: list[dict]) -> list[dict]:
    """Subdivide vs sell whole, for every urban parcel that has a finished-lot price."""
    rows = []
    for p in parcels:
        if p["kind"] == "rural" or not p.get("lot_price_m2"):
            continue
        sub, whole = project(p, strategy="subdivision"), project(p, strategy="whole")
        rows.append(
            {
                "id": p["id"],
                "name": p["name"],
                "area_m2": p["area_m2"],
                "rule": strategy_for(p, config.base()),
                "vgv_subdivision": sub["vgv"],
                "npv_subdivision": sub["npv"],
                "irr_subdivision": sub["irr"],
                "vgv_whole": whole["vgv"],
                "npv_whole": whole["npv"],
                "irr_whole": whole["irr"],
            }
        )
    return rows
