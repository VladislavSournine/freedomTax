"""Parse F1419104 (довідка з ДРФО про доходи) XML export from cabinet.tax.gov.ua.

The XML is WINDOWS-1251 encoded and uses a flat T1RXXXXG{N} schema where each
row is identified by ROWNUM. We only need the numeric fields — agent names and
oznaka descriptions stay in cp1251 but we key off the numeric oznaka code at
the start of T1RXXXXG13S (e.g. "126 - Додаткове благо").

Column mapping (per F1419104 xsd):
    G7  — сума нарахованого доходу
    G9  — ПДФО нараховано
    G11 — ВЗ нараховано
    G13S — "<code> - <oznaka description>"

Rows to skip:
    - G13S starting with "777" — row 30 is the taxpayer's own declaration,
      not an income entry.
    - Rows without G13S (summary row 29) are implicitly skipped.
"""

from __future__ import annotations

import re
from typing import IO, Union

from lxml import etree

_OZNAKA_RE = re.compile(r"^\s*(\d+)")
_SKIP_CODES = {"777"}  # row 30 = taxpayer's own declaration


def parse_f1419104_xml(source: Union[str, bytes, IO]) -> dict:
    """Parse an F1419104 XML and return kwargs for aggregate_drfo_oznakas().

    Returns dict with keys matching aggregate_drfo_oznakas signature, plus
    'row_101_income' / 'row_101_pdfo' / 'row_101_vz' for cross-checking
    ряд. 10.3 (ЗП) from довідка against the taxpayer's own 10.3 entry.
    """
    tree = etree.parse(source) if isinstance(source, (str, bytes)) else etree.parse(source)
    body = tree.find("DECLARBODY")
    if body is None:
        raise ValueError("F1419104 XML: missing DECLARBODY")

    rows: dict[int, dict[str, str]] = {}
    for el in body:
        rn = el.get("ROWNUM")
        if rn is None:
            continue
        rows.setdefault(int(rn), {})[el.tag] = el.text or ""

    sums: dict[str, dict[str, float]] = {}
    for cells in rows.values():
        o_text = cells.get("T1RXXXXG13S", "")
        m = _OZNAKA_RE.match(o_text)
        if not m:
            continue
        code = m.group(1)
        if code in _SKIP_CODES:
            continue
        acc = sums.setdefault(code, {"income": 0.0, "pdfo": 0.0, "vz": 0.0})
        acc["income"] += _to_float(cells.get("T1RXXXXG7"))
        acc["pdfo"] += _to_float(cells.get("T1RXXXXG9"))
        acc["vz"] += _to_float(cells.get("T1RXXXXG11"))

    return {
        "oznaka_125_income": _get(sums, "125", "income"),
        "oznaka_126_income": _get(sums, "126", "income"),
        "oznaka_126_pdfo_withheld": _get(sums, "126", "pdfo"),
        "oznaka_126_vz_withheld": _get(sums, "126", "vz"),
        "oznaka_127_income": _get(sums, "127", "income"),
        "oznaka_127_pdfo_withheld": _get(sums, "127", "pdfo"),
        "oznaka_127_vz_withheld": _get(sums, "127", "vz"),
        "oznaka_160_income": _get(sums, "160", "income"),
        "row_101_income": _get(sums, "101", "income"),
        "row_101_pdfo": _get(sums, "101", "pdfo"),
        "row_101_vz": _get(sums, "101", "vz"),
    }


def _to_float(raw: Union[str, None]) -> float:
    if not raw:
        return 0.0
    try:
        return float(raw.strip())
    except ValueError:
        return 0.0


def _get(sums: dict, code: str, key: str) -> float:
    return round(sums.get(code, {}).get(key, 0.0), 2)
