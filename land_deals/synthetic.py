"""A fictitious portfolio of land parcels: large urban-expansion plots to subdivide, smaller urban areas and rural
small farms to resell whole. Deterministic (seeded). Everything here is invented."""
from __future__ import annotations

import json
import random
from pathlib import Path

from . import config

PLAN = [  # (kind, area range m2, raw land R$/m2 range, finished lot R$/m2 range, how many)
    ("expansion", (25000, 120000), (35, 70), (290, 390), 3),
    ("urban", (22000, 40000), (70, 110), (420, 540), 1),
    ("urban", (6000, 15000), (90, 160), (0, 0), 2),
    ("urban", (1200, 4000), (180, 320), (0, 0), 2),
    ("rural", (30000, 90000), (8, 20), (0, 0), 2),
]
NAMES = {"expansion": ["Gleba Boa Vista", "Gleba Santa Rita", "Gleba Ribeirão Claro"],
         "urban": ["Área Jardim Novo", "Área Vila Operária", "Área Avenida Central", "Terreno Rua das Acácias",
                   "Terreno Esquina Comercial"],
         "rural": ["Chácara Água Limpa", "Sítio Pinheirinho"]}
TOWNS = ["Município A (interior de SP)", "Município B (interior de SP)", "Município C (sul de MG)"]


def generate(path: Path = config.PORTFOLIO, seed: int = 11) -> list[dict]:
    rng = random.Random(seed)
    parcels, used = [], {k: 0 for k in NAMES}
    for kind, (amin, amax), (rmin, rmax), (lmin, lmax), count in PLAN:
        for _ in range(count):
            area = round(rng.uniform(amin, amax), -2)
            raw = round(rng.uniform(rmin, rmax), 0)
            parcels.append({
                "name": NAMES[kind][used[kind]], "kind": kind, "town": rng.choice(TOWNS), "area_m2": area,
                "acquisition_price": round(area * raw * rng.uniform(0.70, 0.90), -3),  # bought below market
                "acquisition_month": rng.randint(0, 15),
                "raw_price_m2": raw,
                "lot_price_m2": round(rng.uniform(lmin, lmax), 0) if lmax else None,
                "overrides": {},
            })
            used[kind] += 1
    parcels.sort(key=lambda p: (p["acquisition_month"], p["name"]))
    for i, p in enumerate(parcels, start=1):
        p["id"] = f"T{i:02d}"
    parcels = [{"id": p.pop("id"), **p} for p in parcels]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(parcels, ensure_ascii=False, indent=1), encoding="utf-8")
    return parcels


def load(path: Path = config.PORTFOLIO) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError("No portfolio yet: run `python generate_data.py` first.")
    return json.loads(path.read_text(encoding="utf-8"))
