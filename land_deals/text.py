"""Small text and number helpers for Brazilian documents: normalization, R$ amounts, dates, amounts in words."""
from __future__ import annotations

import re
import unicodedata
from datetime import date


def fold(s: str | None) -> str:
    """Lowercase, accents removed, dashes unified, whitespace collapsed. Used to compare quotes and names."""
    s = str(s or "").replace("–", "-").replace("—", "-").replace(" ", " ")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def key_part(s: str | None) -> str:
    """Normalized piece of a lot key: 'Loteamento Jardim Primavera' -> 'jardim primavera'."""
    s = fold(s)
    s = re.sub(r"^(loteamento|quadra|lote|qd\.?|lt\.?)\s+", "", s)
    return s.strip(" .,")


_BR_NUMBER = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+,\d+|\d+")


def parse_number(s: str | None) -> float | None:
    """'R$ 1.250.000,00' -> 1250000.0 · '450 m²' -> 450.0 · '1,0% ao mes' -> 1.0 · '36 parcelas' -> 36.0."""
    if s is None:
        return None
    s = str(s).strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", s):            # already plain: '450000.00'
        return float(s)
    m = _BR_NUMBER.search(s)
    if not m:
        return None
    return float(m.group(0).replace(".", "").replace(",", "."))


def parse_date(s: str | None) -> date | None:
    """'15/03/2025' -> date(2025, 3, 15); impossible dates such as 31/02/2025 -> None."""
    if not s:
        return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(s))
    if not m:
        m2 = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(s))
        if not m2:
            return None
        y, mo, d = map(int, m2.groups())
    else:
        d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def brl(v: float) -> str:
    """1250000 -> '1.250.000,00'."""
    return f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def br_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


_UNITS = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze",
          "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
_TENS = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_HUNDREDS = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos",
             "oitocentos", "novecentos"]


def _below_1000(n: int) -> str:
    if n == 100:
        return "cem"
    parts = []
    h, r = divmod(n, 100)
    if h:
        parts.append(_HUNDREDS[h])
    if r:
        parts.append(_UNITS[r] if r < 20 else _TENS[r // 10] + (f" e {_UNITS[r % 10]}" if r % 10 else ""))
    return " e ".join(parts)


def money_words(value: float) -> str:
    """450000 -> 'quatrocentos e cinquenta mil reais'. Whole reais only (prices here are round)."""
    n = int(round(value))
    if n == 0:
        return "zero reais"
    millions, rest = divmod(n, 1_000_000)
    thousands, units = divmod(rest, 1000)
    groups = []
    if millions:
        groups.append("um milhão" if millions == 1 else f"{_below_1000(millions)} milhões")
    if thousands:
        groups.append("mil" if thousands == 1 else f"{_below_1000(thousands)} mil")
    if units:
        groups.append(_below_1000(units))
    text = groups[0]
    if len(groups) > 1:   # "e" before a last group that is round or small, a comma otherwise
        sep = " e " if (not units or units < 100 or units % 100 == 0) else ", "
        text = ", ".join(groups[:-1]) + sep + groups[-1]
    if millions and not thousands and not units:
        return text + " de reais"
    return text + (" real" if n == 1 else " reais")


def words_key(s: str | None) -> str:
    """Comparable form of an amount in words: folded, no punctuation, no connective 'e', no currency word."""
    s = re.sub(r"[^a-z ]", " ", fold(s))
    return " ".join(w for w in s.split() if w not in {"e", "de", "reais", "real"})


def pmt(principal: float, monthly_rate: float, n: int) -> float:
    """Installment of a Price-table (French amortization) loan."""
    if n <= 0:
        return 0.0
    if monthly_rate == 0:
        return principal / n
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** -n)
