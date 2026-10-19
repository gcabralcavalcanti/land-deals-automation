"""Independent check of the model: the same parcels rebuilt with numpy straight from the written spec (README, "The
model"), and the metrics recomputed another way (NPV by vector discounting, IRR from the roots of the NPV polynomial,
payback and exposure from numpy's cumulative sum). Nothing here imports the model's internals except the results."""

import math

import numpy as np
import pytest

from land_deals import config, model, synthetic

H = 400  # months, longer than any parcel


def spec_flows(p: dict, a: dict, strategy: str) -> dict[str, np.ndarray]:
    f = {c: np.zeros(H) for c in model.CATEGORIES}
    t0, area, price = p["acquisition_month"], p["area_m2"], p["acquisition_price"]
    rural = p["kind"] == "rural"
    f["acquisition"][t0] -= price
    f["acquisition_taxes"][t0] -= price * (a["itbi_rate"] + a["deed_registry_rate"]) + (
        a["car_service"] if rural else 0
    )
    share = np.zeros(H)  # share of the area still owned
    if strategy == "subdivision":
        A, I, N = int(a["approval_months"]), int(a["infra_months"]), int(a["absorption_months"])
        lots = math.floor(area * a["saleable_ratio"] / a["lot_size_m2"])
        vgv = lots * p["lot_price_m2"] * a["lot_price_factor"] * a["lot_size_m2"]
        L = t0 + A
        f["studies_approval"][t0:L] -= (a["topography_per_m2"] + a["approval_per_m2"]) * area / A
        f["infrastructure"][L : L + I] -= a["infra_per_m2"] * lots * a["lot_size_m2"] * (1 + a["labor_rate"]) / I
        f["small_constructions"][t0 + 1] -= 4 * math.sqrt(area) * a["fence_per_m"]
        f["small_constructions"][L] -= a["gatehouse"]
        sales = np.zeros(H)
        sales[L : L + N] = vgv / N
        f["marketing"][L : L + N] -= vgv * a["marketing_rate"] / N
        share[t0:L] = 1
        share[L : L + N] = 1 - np.arange(1, N + 1) / N
        down_rate, n, idx = a["down_rate"], int(a["installments"]), a["index_rate_year"]
        cash = sales * a["cash_share"]
        financed = sales * (1 - a["cash_share"])
    else:
        hold = int(a["hold_months"])
        vgv = area * p["raw_price_m2"] * a["lot_price_factor"] * (1 + a["land_appreciation_year"]) ** (hold / 12)
        sales = np.zeros(H)
        sales[t0 + hold] = vgv
        share[t0 : t0 + hold] = 1
        down_rate, n, idx = a["whole_down_rate"], int(a["whole_installments"]), 0.0
        cash = np.zeros(H)
        financed = sales
    i = a["monthly_interest"]
    f["broker"] -= sales * a["broker_rate"]
    f["cash_sales"] += cash
    f["down_payments"] += financed * down_rate
    pmt = (1 - down_rate) * i / (1 - (1 + i) ** -n)  # per R$ financed
    k = np.arange(1, n + 1)
    schedule = np.zeros(n + 1)
    schedule[1:] = pmt * (1 + idx) ** ((k - 1) // 12) * (1 - a["default_rate"])
    f["installments"] += np.convolve(financed, schedule)[:H]
    maint = a["rural_maintenance_per_m2_month"] if rural else a["maintenance_per_m2_month"]
    f["maintenance"] -= maint * area * share
    f["property_tax"] -= (a["itr_rate"] if rural else a["iptu_rate"]) / 12 * price * share
    f["sales_tax"] -= (f["cash_sales"] + f["down_payments"] + f["installments"]) * a["sales_tax_rate"]
    f["_vgv"] = vgv
    return f


def npv_vec(net, year_rate):
    r = (1 + year_rate) ** (1 / 12) - 1
    return float(np.sum(np.asarray(net) / (1 + r) ** np.arange(len(net))))


def irr_roots(net):
    """Annual IRR from the real positive root x = 1/(1+r) of sum(net_k x^k) = 0 (unique sign change here)."""
    roots = np.roots(np.asarray(net, dtype=float)[::-1])
    xs = [z.real for z in roots if abs(z.imag) < 1e-9 and 0 < z.real < 2]
    candidates = [1 / x - 1 for x in xs]
    r = min(candidates, key=lambda c: abs(npv_vec(net, (1 + c) ** 12 - 1)))
    return (1 + r) ** 12 - 1


@pytest.fixture(scope="module")
def parcels(tmp_path_factory):
    return synthetic.generate(tmp_path_factory.mktemp("p") / "portfolio.json")


@pytest.mark.parametrize("pick", ["subdivision", "whole", "rural"])
def test_flows_match_the_spec(parcels, pick):
    a = config.base()
    p = next(
        x
        for x in parcels
        if (x["kind"] == "rural") == (pick == "rural")
        and model.strategy_for(x, a) == ("subdivision" if pick == "subdivision" else "whole")
    )
    r = model.project(p)
    f = spec_flows(p, a, r["strategy"])
    assert r["vgv"] == pytest.approx(f["_vgv"])
    for c in model.CATEGORIES:
        assert r["totals"][c] == pytest.approx(f[c].sum(), rel=1e-9, abs=1e-6), c
    net = sum(f[c] for c in model.CATEGORIES)
    last = int(np.nonzero(np.abs(net) > 1e-9)[0].max())
    net = net[p["acquisition_month"] : last + 1]
    assert np.allclose(r["net"], net, atol=1e-6)
    # metrics, computed another way
    cum = np.cumsum(net)
    trough = int(np.argmin(cum))
    assert r["max_exposure"] == pytest.approx(-cum.min())
    pay = next((k for k in range(trough, len(cum)) if cum[k] >= 0), None)
    assert r["payback_months"] == pay
    assert r["npv"] == pytest.approx(npv_vec(net, a["discount_rate_year"]), rel=1e-9)
    assert r["irr"] == pytest.approx(irr_roots(net), abs=1e-6)


def test_installments_repay_the_balance():
    """Before correction and default, installments discounted at the contract rate equal the financed balance."""
    a = {**config.base(), "index_rate_year": 0.0, "default_rate": 0.0}
    p = {
        "id": "X",
        "name": "x",
        "kind": "urban",
        "area_m2": 30000,
        "acquisition_price": 1e6,
        "acquisition_month": 0,
        "raw_price_m2": 50,
        "lot_price_m2": 400,
        "overrides": {},
    }
    r = model.project(p, a, strategy="subdivision")
    i, L = a["monthly_interest"], r["launch"]
    pv = sum(v / (1 + i) ** (m - L) for m, v in r["by_category"]["installments"].items())
    # sales are spread over months; discount each month's sales back to L the same way
    financed = sum(
        r["vgv"] / a["absorption_months"] * (1 - a["cash_share"]) * (1 - a["down_rate"]) / (1 + i) ** j
        for j in range(int(a["absorption_months"]))
    )
    assert pv == pytest.approx(financed, rel=1e-9)


def test_correction_steps_once_a_year():
    a = {**config.base(), "default_rate": 0.0}
    p = {
        "id": "X",
        "name": "x",
        "kind": "urban",
        "area_m2": 30000,
        "acquisition_price": 1e6,
        "acquisition_month": 0,
        "raw_price_m2": 50,
        "lot_price_m2": 400,
        "overrides": {},
    }
    r = model.project(p, {**a, "absorption_months": 1}, strategy="subdivision")
    inst = [r["by_category"]["installments"][m] for m in sorted(r["by_category"]["installments"])]
    assert len(inst) == a["installments"]
    assert inst[11] == pytest.approx(inst[0]) and inst[12] == pytest.approx(inst[0] * (1 + a["index_rate_year"]))
    assert inst[24] == pytest.approx(inst[0] * (1 + a["index_rate_year"]) ** 2)


def test_sales_curve_spans_the_absorption_period(parcels):
    p = next(x for x in parcels if model.strategy_for(x, config.base()) == "subdivision")
    for months in (24, 36, 48):
        r = model.project(p, {"absorption_months": months})
        sold = [m for m, v in r["by_category"]["cash_sales"].items() if v > 0]
        assert len(sold) == months and min(sold) == r["launch"] and max(sold) == r["sell_out"]


def test_sensitivity_moves_one_assumption_at_a_time(parcels, monkeypatch):
    seen = []
    real = model.portfolio

    def spy(ps, assumptions=None):
        seen.append(dict(assumptions or {}))
        return real(ps, assumptions)

    monkeypatch.setattr(model, "portfolio", spy)
    model.sensitivity(parcels)
    assert seen[0] == {} and all(len(s) == 1 for s in seen[1:])
    assert len(seen) == 1 + 2 * len(model.SENSITIVITY)
