"""Paths, model choice, cost limits and every economic assumption, each with a range and its source.

Source labels: a public rule is cited by name; anything else is marked "illustrative" (a typical value used to make
the model concrete, not market data). Change a value here or override it per parcel in data/portfolio.json.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PORTFOLIO = DATA / "portfolio.json"       # synthetic parcels (versioned), written by generate_data.py
INTAKE = DATA / "intake"                  # free-text parcel descriptions for the AI intake (versioned)
RECORDINGS = ROOT / "recordings"          # recorded LLM answers: response cache + demo mode (versioned)
REPORTS = ROOT / "reports"
OUTPUT = ROOT / "output"
LOGS = ROOT / "logs"                      # one JSON line per LLM call (not versioned)

START = (2026, 1)                         # month 0 of the model (year, month)

# name: (base, low, high, unit, source). low/high feed the sensitivity analysis and the scenarios.
ASSUMPTIONS: dict[str, tuple] = {
    # acquisition
    "itbi_rate": (0.03, 0.02, 0.03, "share of price", "municipal tax; 2-3% is the usual range in SP municipalities (illustrative)"),
    "deed_registry_rate": (0.015, 0.01, 0.02, "share of price", "notary and registry fees follow state tables (illustrative)"),
    # subdivision (loteamento)
    "saleable_ratio": (0.60, 0.55, 0.65, "share of gross area", "streets and public areas are set by municipal law under Lei 6.766/1979 (illustrative)"),
    "lot_size_m2": (300, 250, 360, "m2", "illustrative"),
    "topography_per_m2": (0.5, 0.3, 0.8, "R$/m2 gross", "illustrative"),
    "approval_per_m2": (2.5, 1.5, 4.0, "R$/m2 gross", "urban, environmental and city approval projects (illustrative)"),
    "approval_months": (12, 8, 24, "months", "illustrative"),
    "infra_per_m2": (110.0, 80.0, 160.0, "R$/m2 saleable", "streets, drainage, water, sewage, power (illustrative)"),
    "infra_months": (12, 9, 18, "months", "illustrative"),
    "labor_rate": (0.08, 0.05, 0.12, "share of infrastructure", "site labor and management (illustrative)"),
    "gatehouse": (80000.0, 50000.0, 120000.0, "R$ per subdivision", "small constructions: gatehouse and sales stand (illustrative)"),
    "fence_per_m": (60.0, 40.0, 90.0, "R$/m of perimeter", "illustrative"),
    "marketing_rate": (0.015, 0.01, 0.025, "share of VGV", "illustrative"),
    # holding
    "maintenance_per_m2_month": (0.08, 0.05, 0.12, "R$/m2 of unsold area per month", "cleaning, mowing, fence repairs (illustrative)"),
    "iptu_rate": (0.01, 0.006, 0.015, "share of land value per year", "urban property tax, municipal (illustrative)"),
    "itr_rate": (0.003, 0.0003, 0.01, "share of land value per year", "rural land tax, rate table of Lei 9.393/1996 (0.03% to 20%); low-use small areas assumed"),
    "car_service": (2500.0, 1500.0, 4000.0, "R$ once per rural parcel", "CAR registration is free (SICAR); this is the surveyor's fee (illustrative)"),
    # sale
    "broker_rate": (0.05, 0.04, 0.06, "share of sale price", "illustrative"),
    "sales_tax_rate": (0.0593, 0.0593, 0.0593, "share of receipts", "Lucro Presumido: IRPJ 1.2% + CSLL 1.08% (Lei 9.249/1995) + PIS 0.65% + COFINS 3% (Lei 9.718/1998)"),
    "absorption_months": (36, 24, 48, "months to sell all lots", "author's experience: return takes 2-4 years on average"),
    "lot_price_factor": (1.0, 0.85, 1.10, "x the parcel's lot price/m2", "scenario lever"),
    # payment
    "cash_share": (0.30, 0.20, 0.40, "share of sales paid in cash", "illustrative"),
    "down_rate": (0.20, 0.10, 0.30, "share of price at signing", "illustrative"),
    "installments": (60, 36, 120, "months", "illustrative"),
    "monthly_interest": (0.008, 0.005, 0.01, "per month, Price table", "illustrative"),
    "index_rate_year": (0.045, 0.035, 0.06, "per year, fixed", "correction index (IPCA by default) as a fixed assumption, no real series"),
    "default_rate": (0.01, 0.0, 0.03, "share of installments never received", "author's experience: delinquency is rare"),
    # whole-lot resale
    "hold_months": (30, 24, 48, "months until the whole parcel is sold", "author's experience: 2-4 years"),
    "land_appreciation_year": (0.06, 0.03, 0.09, "per year", "illustrative"),
    "whole_down_rate": (0.40, 0.30, 0.50, "share of price at signing", "illustrative"),
    "whole_installments": (12, 6, 24, "months", "illustrative"),
    # decision
    "discount_rate_year": (0.14, 0.11, 0.18, "per year", "hurdle rate; compare with the Selic of the day (illustrative)"),
    "subdivision_min_m2": (20000, 20000, 20000, "m2", "parcels at least this big and urban or urban-expansion are subdivided; smaller ones are sold whole"),
}
INDEX_NAME = os.environ.get("LAND_INDEX", "IPCA")


def base() -> dict:
    return {k: v[0] for k, v in ASSUMPTIONS.items()}


# ---------------------------------------------------------------- model and limits
MODEL = os.environ.get("LAND_MODEL", "claude-haiku-5-5")
PRICE_PER_MTOK = {"claude-haiku-5-5": (0.10, 0.50)}  # USD (input, output), Anthropic price list
MAX_CALLS_PER_RUN = int(os.environ.get("LAND_MAX_CALLS", "20"))
MAX_TOKENS = {"intake": 900, "memo": 900}
TIMEOUT_S = 60.0
SDK_RETRIES = 2                     # network/429/5xx retries done by the SDK
SCHEMA_RETRIES = 1                  # one extra call if the answer fails the schema or the number check
