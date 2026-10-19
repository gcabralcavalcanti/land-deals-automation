"""AI intake: a free-text description of a parcel becomes structured premises, which a person confirms before they
enter the portfolio. The model copies values with a quote; Python converts units, validates and fills defaults."""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import config
from .llm import LLM
from .text import fold, parse_number

FIELDS = {
    "name": "short name for the parcel (make one up from the description if none is given)",
    "kind": "one of: urban, expansion (urban-expansion zone), rural",
    "town": "town or region, as written",
    "area": "total area as written, with its unit (m2, hectares, alqueires)",
    "acquisition_price": "price the buyer expects to pay, as written (if an asking price and an expected closing price both appear, the expected closing price)",
    "raw_price_m2": "market price of comparable raw land per m2, as written",
    "lot_price_m2": "market price per m2 of finished lots nearby, as written; empty if not mentioned",
}

SYSTEM = """You turn a free-text description of a land parcel into structured premises for an investment model.
Rules:
- Copy values as written, with their units ("12 hectares", "R$ 3,8 milhões"). Do not convert or compute.
- kind is the only field you classify: urban, expansion or rural.
- quote: the exact passage of the description that supports the value; "" when the value is empty.
- If the description does not give a field, value and quote are "" (name is the exception).
- notes: one sentence on anything a buyer should double-check, or ""."""


def schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string", "enum": list(FIELDS)},
                        "value": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                    "required": ["field", "value", "quote"],
                    "additionalProperties": False,
                },
            },
            "notes": {"type": "string"},
        },
        "required": ["items", "notes"],
        "additionalProperties": False,
    }


def answer_problems(answer: dict) -> list[str]:
    names = [it["field"] for it in answer["items"]]
    return [f"field {n!r} answered {names.count(n)} times" for n in FIELDS if names.count(n) != 1]


UNITS_M2 = {"hectare": 10000, "ha": 10000, "alqueire": 24200, "m2": 1, "m²": 1, "metro": 1}


def parse_area(s: str | None) -> float | None:
    """'12 hectares' -> 120000 · '3 alqueires paulistas' -> 72600 · '1.800 m²' -> 1800."""
    n = parse_number(s)
    if n is None:
        return None
    low = fold(s)
    for unit, factor in UNITS_M2.items():
        if re.search(rf"\b{unit}", low):
            return n * factor
    return n


def parse_money(s: str | None) -> float | None:
    """'R$ 3,8 milhões' -> 3800000 · 'R$ 650 mil' -> 650000 · 'R$ 540.000' -> 540000."""
    n = parse_number(s)
    if n is None:
        return None
    low = fold(s)
    if re.search(r"\bmilh(ao|oes)\b|\bmi\b", low):
        return n * 1_000_000
    if re.search(r"\bmil\b", low):
        return n * 1000
    return n


def to_parcel(answer: dict, text: str) -> dict:
    """Validated premises + where each one came from (text or default) + problems a person must look at."""
    got = {it["field"]: it for it in answer["items"]}
    problems, source = [], {}
    folded = fold(text)
    for f, it in got.items():
        if it["value"].strip() and f not in ("name", "kind") and fold(it["quote"]) not in folded:
            problems.append(f"{f}: the quoted passage is not in the description")
    kind = got["kind"]["value"].strip().lower()
    if kind not in ("urban", "expansion", "rural"):
        problems.append(f"kind {kind!r} is not urban, expansion or rural")
        kind = "urban"
    area = parse_area(got["area"]["value"])
    price = parse_money(got["acquisition_price"]["value"])
    raw = parse_money(got["raw_price_m2"]["value"])
    lot = parse_money(got["lot_price_m2"]["value"])
    if not area or area <= 0:
        problems.append("area is missing or not a number")
    if not price or price <= 0:
        problems.append("acquisition price is missing or not a number")
    for f, v in (("area", area), ("acquisition_price", price), ("raw_price_m2", raw), ("lot_price_m2", lot)):
        source[f] = "text" if v else "default"
    if not raw and area and price:
        raw = round(price / area, 2)  # default: bought at market
    parcel = {
        "name": got["name"]["value"].strip() or "New parcel",
        "kind": kind,
        "town": got["town"]["value"].strip() or "not given",
        "area_m2": area,
        "acquisition_price": price,
        "acquisition_month": 0,
        "raw_price_m2": raw,
        "lot_price_m2": lot,
        "overrides": {},
    }
    return {
        "parcel": parcel,
        "source": source,
        "problems": problems,
        "notes": answer.get("notes", ""),
        "quotes": {f: it["quote"] for f, it in got.items()},
    }


def run(llm: LLM, path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    lines = "\n".join(f"- {k}: {v}" for k, v in FIELDS.items())
    prompt = f"Fields (one item per field):\n{lines}\n\n<description>\n{text}\n</description>"
    answer = llm.ask(
        f"intake-{path.stem}", SYSTEM, prompt, schema(), check=answer_problems, max_tokens=config.MAX_TOKENS["intake"]
    )
    return {"file": path.name, **to_parcel(answer, text)}


def accept(result: dict, portfolio_path: Path = config.PORTFOLIO) -> dict:
    if result["problems"]:
        raise ValueError("fix the problems before accepting: " + "; ".join(result["problems"]))
    parcels = json.loads(portfolio_path.read_text(encoding="utf-8"))
    new = {"id": f"T{len(parcels) + 1:02d}", **result["parcel"]}
    parcels.append(new)
    portfolio_path.write_text(json.dumps(parcels, ensure_ascii=False, indent=1), encoding="utf-8")
    return new
