"""Text and number helpers for Brazilian inputs: accent folding, R$ amounts, the Price-table installment."""

from __future__ import annotations

import re
import unicodedata


def fold(s: str | None) -> str:
    """Lowercase, accents removed, dashes unified, whitespace collapsed. Used to compare quotes."""
    s = str(s or "").replace("–", "-").replace("—", "-").replace(" ", " ")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


_BR_NUMBER = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+,\d+|\d+")


def parse_number(s: str | None) -> float | None:
    """'R$ 1.250.000,00' -> 1250000.0 · '450 m²' -> 450.0 · '3,8 milhões' -> 3.8 (the unit is applied elsewhere)."""
    if s is None:
        return None
    s = str(s).strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", s):  # already plain: '450000.00'
        return float(s)
    m = _BR_NUMBER.search(s)
    if not m:
        return None
    return float(m.group(0).replace(".", "").replace(",", "."))


def pmt(principal: float, monthly_rate: float, n: int) -> float:
    """Installment of a Price-table (French amortization) loan."""
    if n <= 0:
        return 0.0
    if monthly_rate == 0:
        return principal / n
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** -n)
