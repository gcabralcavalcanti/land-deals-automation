"""AI investment memo per parcel. The model writes from a fixed list of facts computed by the model; Python checks
that every number in the memo is one of those facts and that the recommendation agrees with the NPV."""

from __future__ import annotations

import re

from . import config
from .llm import LLM

SYSTEM = """You are an analyst at a land development company. Write a short investment memo for one parcel, for a
partner who reads fast: plain English, short sentences, the decision first.
Rules:
- Use only the numbers in FACTS, written exactly as they appear there (same format, same rounding). Write no other
  number: no new totals, no differences, no ratios, no years.
- recommendation: invest, invest_with_conditions or do_not_invest. A negative NPV at the hurdle rate cannot be
  "invest".
- headline: one sentence. thesis: 2 to 4 sentences. risks: 2 or 3 short items. conditions: 0 to 2 short items
  (what would have to be true to invest)."""

SCHEMA = {
    "type": "object",
    "properties": {
        "recommendation": {"type": "string", "enum": ["invest", "invest_with_conditions", "do_not_invest"]},
        "headline": {"type": "string"},
        "thesis": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
        "conditions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["recommendation", "headline", "thesis", "risks", "conditions"],
    "additionalProperties": False,
}

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def money(v: float) -> str:
    return f"R$ {v:,.0f}"


def pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def facts(p: dict, hurdle: float) -> dict[str, str]:
    f = {
        "parcel": f"{p['id']} {p['name']}",
        "kind": p["kind"],
        "strategy": p["strategy"],
        "area": f"{p['area_m2']:,.0f} m2",
        "acquisition price": money(-p["totals"]["acquisition"]),
        "VGV (total sales value)": money(p["vgv"]),
        "net profit (nominal)": money(p["profit"]),
        "margin on VGV": pct(p["margin"]),
        f"NPV at the {pct(hurdle)} hurdle rate": money(p["npv"]),
        "IRR (per year)": pct(p["irr"]),
        "hurdle rate": pct(hurdle),
        "maximum cash exposure": money(p["max_exposure"]),
        "payback": f"{p['payback_months']} months" if p["payback_months"] is not None else "not reached",
        "cash flow duration": f"{p['duration_months']} months",
        "holding costs (maintenance + property tax)": money(
            -(p["totals"]["maintenance"] + p["totals"]["property_tax"])
        ),
    }
    if p["strategy"] == "subdivision":
        f["infrastructure and site labor"] = money(-p["totals"]["infrastructure"])
        f["lots"] = f"{p['lots']} lots"
        f["price per lot"] = money(p["lot_price"])
        f["months from purchase to launch"] = f"{p['launch'] - p['start']} months"
    return f


def allowed_numbers(fs: dict[str, str]) -> set[str]:
    return {m.replace(",", "") for v in list(fs.values()) + list(fs.keys()) for m in _NUM.findall(v)}


def check(answer: dict, fs: dict[str, str], npv: float) -> list[str]:
    text = " ".join([answer["headline"], answer["thesis"], *answer["risks"], *answer["conditions"]])
    ok = allowed_numbers(fs)
    bad = sorted({m for m in _NUM.findall(text) if m.replace(",", "") not in ok and len(m.replace(",", "")) > 1})
    out = [f"number {b} is not in FACTS" for b in bad]
    if npv < 0 and answer["recommendation"] == "invest":
        out.append("recommendation 'invest' with a negative NPV")
    if not 2 <= len(answer["risks"]) <= 3:
        out.append("risks must have 2 or 3 items")
    return out


def write(llm: LLM, p: dict, hurdle: float = config.base()["discount_rate_year"]) -> dict:
    fs = facts(p, hurdle)
    prompt = "FACTS\n" + "\n".join(f"- {k}: {v}" for k, v in fs.items())
    try:
        answer = llm.ask(
            f"memo-{p['id']}",
            SYSTEM,
            prompt,
            SCHEMA,
            check=lambda a: check(a, fs, p["npv"]),
            max_tokens=config.MAX_TOKENS["memo"],
        )
        return {"id": p["id"], "status": "checked", "facts": fs, **answer}
    except ValueError as e:  # failed the checks twice: keep it out of the reports
        return {"id": p["id"], "status": f"rejected by the checks: {e}", "facts": fs}
