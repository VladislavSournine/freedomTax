"""Patch a draft F0100215 XML with computed Freedom24 values.

The user's typical workflow: open ЕК → start a new declaration (F0100215) →
fill the easy parts (HNAME/HCITY/HSTREET, salary R0103, agent income R01013
from F1419104, real-estate table T1) → download the draft XML → run it
through this patcher to add Freedom24 row 10.10 (foreign passive income) and
optionally row 10.8 (trades from Ф1), plus recompute the cross-validated
sums (R010, R012, R013, R0201, R0211).

Why patch rather than generate from scratch: the form has ~50 user-specific
fields we'd otherwise have to ask about (region code C_REG/C_RAJ, address
parts, CABINET software version, real-estate ownership). Patching keeps
those untouched and only fills the gap that ЕК itself cannot infer.

Tag scheme: ``R0`` + 2-digit row + optional subrow digits + ``G`` + col.
E.g. R010G3 = row 10 col 3 total; R0103G3 = row 10.3 col 3 (salary subrow);
R01010G3 = row 10.10 col 3 (foreign subrow). Columns: G3 income, G4 ПДФО
withheld by agent, G5 ВЗ withheld, G6 ПДФО self-calculated, G7 ВЗ
self-calculated, G2S country/currency string.
"""
from __future__ import annotations

import re

from lxml import etree

# G2S string for the foreign-income row. Freedom24 pays in USD via Estonian
# entity, but the income source country reported on Form 1042-S is the US.
_FOREIGN_G2S = "США, долар США (USD)"

# Match a row tag like "R0103G4", "R01010G6", or the string variant "R01010G2S".
# Layout: "R0" + 2-digit main row + 0+ subrow digits + "G" + 1+ col digits +
# optional trailing "S" (string column, e.g. country name for 10.10).
_ROW_TAG_RE = re.compile(r"^R0(\d{2})(\d*)G(\d+)S?$")
# Subrows of row 10 whose value is numeric — drives the R010Gn recompute.
# Trailing S intentionally excluded (G2S is a string, not a summand).
_R10_SUBROW_RE = re.compile(r"^R010\d+G(\d+)$")
# Subrows of row 11 (non-taxable). In practice only G3 exists (income only, no tax).
_R11_SUBROW_RE = re.compile(r"^R011\d+G(\d+)$")
_NIL_ATTR = "{http://www.w3.org/2001/XMLSchema-instance}nil"


def patch_declaration_xml(
    xml_bytes: bytes,
    foreign_income: float = 0.0,
    pdfo_foreign: float = 0.0,
    vz_foreign: float = 0.0,
    trades_profit: float = 0.0,
    pdfo_trades: float = 0.0,
    vz_trades: float = 0.0,
    row_10_13_income: float = 0.0,
    row_10_13_pdfo: float = 0.0,
    row_10_13_vz: float = 0.0,
    row_11_3_income: float = 0.0,
) -> bytes:
    """Inject Freedom24 rows into a draft F0100215 XML and recompute sums.

    Besides Freedom24 10.10 and 10.8, also injects F1419104 agent rows —
    10.13 (ознаки 126 + 127, agent withheld tax) and 11.3 (ознаки 125 + 160,
    non-taxable). Passing 0 (default) leaves those untouched so this stays
    backwards-compatible with callers that only fill Freedom24 rows.
    """
    root = etree.fromstring(xml_bytes)
    body = root.find("DECLARBODY")
    if body is None:
        raise ValueError("XML has no DECLARBODY — not an F0100215 draft")

    if foreign_income > 0:
        _set(body, "R01010G2S", _FOREIGN_G2S)
        _set(body, "R01010G3", _fmt(foreign_income))
        _set(body, "R01010G6", _fmt(pdfo_foreign))
        _set(body, "R01010G7", _fmt(vz_foreign))

    if trades_profit > 0:
        _set(body, "R0108G3", _fmt(trades_profit))
        _set(body, "R0108G6", _fmt(pdfo_trades))
        _set(body, "R0108G7", _fmt(vz_trades))

    if row_10_13_income > 0:
        _set(body, "R01013G3", _fmt(row_10_13_income))
        _set(body, "R01013G4", _fmt(row_10_13_pdfo))
        _set(body, "R01013G5", _fmt(row_10_13_vz))

    if row_11_3_income > 0:
        _set(body, "R0113G3", _fmt(row_11_3_income))

    # Recompute R010G3..G7 = Σ subrow Gn. ЕК validator's cross-check.
    for col in range(3, 8):
        total = sum(
            _read(child)
            for child in body
            if (m := _R10_SUBROW_RE.match(child.tag)) and int(m.group(1)) == col
        )
        _set(body, f"R010G{col}", _fmt(total))

    # Recompute R011G3 = Σ R011X G3, but only if we (a) just inserted R0113 or
    # (b) the draft already carries a real R011G3 total. Drafts from ЕК often
    # ship R0113G3 as an xsi:nil placeholder — we must not materialise that as
    # 0.00 unless the user actually has row-11 data.
    r011_existing = body.find("R011G3")
    r011_is_real = r011_existing is not None and _NIL_ATTR not in r011_existing.attrib
    if row_11_3_income > 0 or r011_is_real:
        total_11 = sum(
            _read(child)
            for child in body
            if (m := _R11_SUBROW_RE.match(child.tag)) and int(m.group(1)) == 3
        )
        _set(body, "R011G3", _fmt(total_11))

    # Section-1 dependent sums.
    r010_g3 = _read(body.find("R010G3"))
    r011_g3 = _read(body.find("R011G3"))
    r010_g6 = _read(body.find("R010G6"))
    r010_g7 = _read(body.find("R010G7"))
    _set(body, "R012G3", _fmt(r010_g3 + r011_g3))
    _set(body, "R013G3", _fmt(r010_g6))

    # Section 4 — ПДФО (R0201) and ВЗ (R0211) до сплати.
    _set(body, "R0201G3", _fmt(r010_g6))
    _set(body, "R0211G3", _fmt(r010_g7))

    return etree.tostring(
        root, encoding="windows-1251", xml_declaration=True, standalone=False
    )


def _set(body, tag: str, value: str):
    """Upsert a child by tag, inserting at the schema-correct position."""
    el = body.find(tag)
    if el is not None:
        el.text = value
        # If the slot was a placeholder (xsi:nil="true"), strip the attr.
        if _NIL_ATTR in el.attrib:
            del el.attrib[_NIL_ATTR]
        return el

    new_el = etree.Element(tag)
    new_el.text = value
    new_key = _row_key(tag)

    if new_key is not None:
        # Insert before the first row sibling whose key is strictly greater —
        # keeps subrows in numeric order so the XSD <xs:sequence> validates.
        for sibling in body:
            sk = _row_key(sibling.tag)
            if sk is not None and sk > new_key:
                sibling.addprevious(new_el)
                return new_el

    # No suitable position found — drop it just before the trailing footer.
    hfill = body.find("HFILL")
    if hfill is not None:
        hfill.addprevious(new_el)
    else:
        body.append(new_el)
    return new_el


def _row_key(tag: str) -> tuple[int, int, int] | None:
    m = _ROW_TAG_RE.match(tag)
    if m is None:
        return None
    return (int(m.group(1)), int(m.group(2) or 0), int(m.group(3)))


def _read(el) -> float:
    if el is None or not el.text:
        return 0.0
    try:
        return float(el.text.strip())
    except ValueError:
        return 0.0


def _fmt(value: float) -> str:
    return f"{round(value, 2):.2f}"
