"""Tests for src.xml_patcher.

Fixture mirrors a real user draft (downloaded from ЕК): salary in R0103,
agent income from F1419104 in R01013, no R01010 yet — exactly the case
that triggers the ^R010G6[0] cross-validator error.
"""
from __future__ import annotations

import re

import pytest
from lxml import etree

from src.xml_patcher import patch_declaration_xml


def _draft(extra_body: str = "") -> bytes:
    """Render a minimal F0100215 draft as cp1251 bytes.

    Only carries the fields the patcher reads or writes; everything else is
    skipped so the test stays focused on the math, not on header plumbing.
    """
    xml = f"""<?xml version="1.0" encoding="windows-1251"?>
<DECLAR xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="F0100215.xsd">
    <DECLARHEAD>
        <TIN>2745810755</TIN>
        <PERIOD_YEAR>2025</PERIOD_YEAR>
    </DECLARHEAD>
    <DECLARBODY>
        <HNAME>SURNAME NAME</HNAME>
        <R010G3>3736734.12</R010G3>
        <R010G4>187585.25</R010G4>
        <R010G5>186836.72</R010G5>
        <R010G6>0.00</R010G6>
        <R010G7>0.00</R010G7>
        <R0103G3>3730976.20</R0103G3>
        <R0103G4>186548.82</R0103G4>
        <R0103G5>186548.81</R0103G5>
        <R01011G3>0.00</R01011G3>
        <R01013G3>5757.92</R01013G3>
        <R01013G4>1036.43</R01013G4>
        <R01013G5>287.91</R01013G5>
        <R011G3>18299.75</R011G3>
        <R0113G3>18299.75</R0113G3>
        <R012G3>3755033.87</R012G3>
        <R013G3>0.00</R013G3>
        <R0201G3>0.00</R0201G3>
        <R0211G3>0.00</R0211G3>
        <T1RXXXXG2 ROWNUM="1">3</T1RXXXXG2>
        <T1RXXXXG7 ROWNUM="1" xsi:nil="true"/>
{extra_body}        <HFILL>17042026</HFILL>
        <HBOS>SURNAME NAME</HBOS>
    </DECLARBODY>
</DECLAR>"""
    return xml.encode("windows-1251")


def _parse(out: bytes):
    return etree.fromstring(out).find("DECLARBODY")


def _text(body, tag: str) -> str:
    el = body.find(tag)
    assert el is not None, f"<{tag}> missing"
    return (el.text or "").strip()


# --- inserts and totals ---


def test_inserts_freedom24_row_with_country():
    out = patch_declaration_xml(
        _draft(),
        foreign_income=15000.50,
        pdfo_foreign=1350.05,
        vz_foreign=750.03,
    )
    body = _parse(out)
    assert "США" in _text(body, "R01010G2S")
    assert _text(body, "R01010G3") == "15000.50"
    assert _text(body, "R01010G6") == "1350.05"
    assert _text(body, "R01010G7") == "750.03"


def test_recomputes_r010_sums_after_insert():
    out = patch_declaration_xml(_draft(), foreign_income=15000.50,
                                pdfo_foreign=1350.05, vz_foreign=750.03)
    body = _parse(out)
    # R010G3 = R0103G3 + R01010G3 + R01011G3 + R01013G3
    #        = 3730976.20 + 15000.50 + 0.00 + 5757.92 = 3751734.62
    assert _text(body, "R010G3") == "3751734.62"
    # G4 unchanged (foreign agent didn't withhold via UA): salary + agent
    assert _text(body, "R010G4") == "187585.25"
    assert _text(body, "R010G5") == "186836.72"
    # G6 == self-calculated PDFO (only R01010 contributes)
    assert _text(body, "R010G6") == "1350.05"
    assert _text(body, "R010G7") == "750.03"


def test_recomputes_section_dependent_sums():
    out = patch_declaration_xml(_draft(), foreign_income=15000.50,
                                pdfo_foreign=1350.05, vz_foreign=750.03)
    body = _parse(out)
    # R012 = R010G3 + R011G3 = 3751734.62 + 18299.75 = 3770034.37
    assert _text(body, "R012G3") == "3770034.37"
    # R013 (PDFO до сплати) = R010G6
    assert _text(body, "R013G3") == "1350.05"
    # Section 4
    assert _text(body, "R0201G3") == "1350.05"
    assert _text(body, "R0211G3") == "750.03"


def test_with_trades_inserts_r0108_and_includes_in_sums():
    out = patch_declaration_xml(
        _draft(),
        foreign_income=15000.50, pdfo_foreign=1350.05, vz_foreign=750.03,
        trades_profit=1000.00, pdfo_trades=180.00, vz_trades=50.00,
    )
    body = _parse(out)
    assert _text(body, "R0108G3") == "1000.00"
    assert _text(body, "R0108G6") == "180.00"
    assert _text(body, "R0108G7") == "50.00"
    # R010G3 += 1000, R010G6 += 180, R010G7 += 50
    assert _text(body, "R010G3") == "3752734.62"
    assert _text(body, "R010G6") == "1530.05"
    assert _text(body, "R010G7") == "800.03"
    assert _text(body, "R0201G3") == "1530.05"
    assert _text(body, "R0211G3") == "800.03"


def test_no_freedom24_skips_r01010():
    """All-zero call still recomputes (cleans up wrong totals) but doesn't add R01010."""
    out = patch_declaration_xml(_draft())
    body = _parse(out)
    assert body.find("R01010G3") is None
    assert body.find("R01010G2S") is None
    assert body.find("R0108G3") is None
    # Totals recomputed from existing subrows only
    assert _text(body, "R010G3") == "3736734.12"  # 3730976.20 + 0 + 5757.92
    assert _text(body, "R010G6") == "0.00"


# --- preserved fields ---


def test_preserves_user_rows():
    out = patch_declaration_xml(_draft(), foreign_income=100.0)
    body = _parse(out)
    # Salary, agent income, row 11.3, header — all untouched
    assert _text(body, "R0103G3") == "3730976.20"
    assert _text(body, "R0103G4") == "186548.82"
    assert _text(body, "R01013G3") == "5757.92"
    assert _text(body, "R01013G4") == "1036.43"
    assert _text(body, "R0113G3") == "18299.75"
    assert _text(body, "R011G3") == "18299.75"
    assert _text(body, "HNAME") == "SURNAME NAME"
    # Header preserved
    head = etree.fromstring(out).find("DECLARHEAD")
    assert head.find("TIN").text == "2745810755"
    assert head.find("PERIOD_YEAR").text == "2025"


def test_preserves_t1_table_with_xsi_nil():
    out = patch_declaration_xml(_draft(), foreign_income=100.0)
    body = _parse(out)
    # T1 row 1 col 7 was xsi:nil="true" — must remain so
    t1g7 = body.find("T1RXXXXG7")
    assert t1g7 is not None
    nil_attr = "{http://www.w3.org/2001/XMLSchema-instance}nil"
    assert t1g7.get(nil_attr) == "true"


# --- ordering (XSD <xs:sequence>) ---


def test_r01010_inserted_in_numeric_order():
    """R01010 must land between R0103 (10.3) and R01011 (10.11)."""
    out = patch_declaration_xml(_draft(), foreign_income=100.0,
                                pdfo_foreign=10.0, vz_foreign=5.0)
    body = _parse(out)
    tags = [child.tag for child in body]
    # R01010 group (G2S, G3, G6, G7) sits after the last R0103* and before R01011
    last_r0103 = max(i for i, t in enumerate(tags) if t.startswith("R0103"))
    first_r01011 = min(i for i, t in enumerate(tags) if t.startswith("R01011"))
    r01010_indices = [i for i, t in enumerate(tags) if t.startswith("R01010")]
    assert r01010_indices, "R01010 elements not found"
    assert all(last_r0103 < i < first_r01011 for i in r01010_indices)


def test_r0108_inserted_before_r01010():
    """Row 10.8 must precede 10.10 in the sequence."""
    out = patch_declaration_xml(
        _draft(),
        foreign_income=100.0, pdfo_foreign=10.0, vz_foreign=5.0,
        trades_profit=200.0, pdfo_trades=36.0, vz_trades=10.0,
    )
    body = _parse(out)
    tags = [child.tag for child in body]
    last_r0108 = max(i for i, t in enumerate(tags) if t.startswith("R0108"))
    first_r01010 = min(i for i, t in enumerate(tags) if t.startswith("R01010"))
    assert last_r0108 < first_r01010


# --- output format ---


def test_output_is_cp1251_with_xml_declaration():
    out = patch_declaration_xml(_draft(), foreign_income=100.0,
                                pdfo_foreign=10.0, vz_foreign=5.0)
    assert isinstance(out, bytes)
    assert out.startswith(b"<?xml")
    assert b"windows-1251" in out[:80].lower()
    # Cyrillic country string round-trips through cp1251
    assert "США".encode("windows-1251") in out


def test_idempotent_when_called_twice():
    """Patch then patch again with same inputs — result identical."""
    once = patch_declaration_xml(_draft(), foreign_income=15000.50,
                                 pdfo_foreign=1350.05, vz_foreign=750.03)
    twice = patch_declaration_xml(once, foreign_income=15000.50,
                                  pdfo_foreign=1350.05, vz_foreign=750.03)
    # Compare normalized whitespace since lxml may re-flow
    norm = lambda b: re.sub(rb"\s+", b" ", b).strip()
    assert norm(once) == norm(twice)


# --- F1419104 agent rows (10.13 and 11.3) ---


def _draft_empty() -> bytes:
    """Mimic a fresh 'Звітна нова' draft downloaded from ЕК: salary filled,
    R0113 present as xsi:nil placeholder, no R01013 / R01010 yet.
    """
    xml = """<?xml version="1.0" encoding="windows-1251"?>
<DECLAR xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="F0100215.xsd">
    <DECLARHEAD>
        <TIN>2745810755</TIN>
        <PERIOD_YEAR>2025</PERIOD_YEAR>
    </DECLARHEAD>
    <DECLARBODY>
        <HNAME>SURNAME NAME</HNAME>
        <R01011G3>0.00</R01011G3>
        <R0103G3>3730976.20</R0103G3>
        <R0103G4>186548.82</R0103G4>
        <R0103G5>186548.81</R0103G5>
        <R0113G3 xsi:nil="true"/>
        <HFILL>17042026</HFILL>
        <HBOS>SURNAME NAME</HBOS>
    </DECLARBODY>
</DECLAR>"""
    return xml.encode("windows-1251")


def test_inserts_row_10_13_when_agent_income_provided():
    out = patch_declaration_xml(
        _draft_empty(),
        row_10_13_income=5757.92,
        row_10_13_pdfo=1036.43,
        row_10_13_vz=287.91,
    )
    body = _parse(out)
    assert _text(body, "R01013G3") == "5757.92"
    assert _text(body, "R01013G4") == "1036.43"
    assert _text(body, "R01013G5") == "287.91"


def test_inserts_row_11_3_and_recomputes_r011():
    out = patch_declaration_xml(
        _draft_empty(),
        row_11_3_income=18299.75,
    )
    body = _parse(out)
    assert _text(body, "R0113G3") == "18299.75"
    assert _text(body, "R011G3") == "18299.75"


def test_row_11_3_strips_xsi_nil_placeholder():
    out = patch_declaration_xml(_draft_empty(), row_11_3_income=100.0)
    body = _parse(out)
    r0113 = body.find("R0113G3")
    nil_attr = "{http://www.w3.org/2001/XMLSchema-instance}nil"
    assert r0113.get(nil_attr) is None
    assert r0113.text == "100.00"


def test_all_fields_together_recomputes_r012():
    out = patch_declaration_xml(
        _draft_empty(),
        foreign_income=15000.50, pdfo_foreign=1350.05, vz_foreign=750.03,
        row_10_13_income=5757.92, row_10_13_pdfo=1036.43, row_10_13_vz=287.91,
        row_11_3_income=18299.75,
    )
    body = _parse(out)
    # R010G3 = 3730976.20 (10.3) + 0.00 (10.11) + 5757.92 (10.13) + 15000.50 (10.10)
    #        = 3751734.62
    assert _text(body, "R010G3") == "3751734.62"
    # R010G4 = 186548.82 (10.3) + 1036.43 (10.13) = 187585.25
    assert _text(body, "R010G4") == "187585.25"
    # R010G5 = 186548.81 (10.3) + 287.91 (10.13) = 186836.72
    assert _text(body, "R010G5") == "186836.72"
    assert _text(body, "R010G6") == "1350.05"
    assert _text(body, "R010G7") == "750.03"
    # R011G3 = 18299.75 (only 11.3)
    assert _text(body, "R011G3") == "18299.75"
    # R012G3 = R010G3 + R011G3 = 3751734.62 + 18299.75 = 3770034.37
    assert _text(body, "R012G3") == "3770034.37"


def test_agent_rows_insert_in_numeric_order():
    """R01013 must land between R01011 and R0113 (then R011 follows)."""
    out = patch_declaration_xml(
        _draft_empty(),
        row_10_13_income=100.0, row_10_13_pdfo=10.0, row_10_13_vz=5.0,
        row_11_3_income=200.0,
    )
    body = _parse(out)
    tags = [child.tag for child in body]
    last_r01011 = max(i for i, t in enumerate(tags) if t.startswith("R01011"))
    first_r01013 = min(i for i, t in enumerate(tags) if t.startswith("R01013"))
    first_r0113 = tags.index("R0113G3")
    last_r01013 = max(i for i, t in enumerate(tags) if t.startswith("R01013"))
    assert last_r01011 < first_r01013
    assert last_r01013 < first_r0113


def test_empty_draft_with_no_agent_data_does_not_force_r011():
    """No R011X subrows and no row_11_3 input → R011G3 absent (stay untouched)."""
    out = patch_declaration_xml(_draft_empty())
    body = _parse(out)
    # R0113G3 xsi:nil still there (we didn't patch it), and R011G3 not inserted
    assert body.find("R011G3") is None


# --- error handling ---


def test_invalid_xml_raises():
    with pytest.raises(etree.XMLSyntaxError):
        patch_declaration_xml(b"<?xml version='1.0'?><not closed")


def test_missing_declarbody_raises():
    bad = b"<?xml version='1.0' encoding='windows-1251'?><DECLAR><DECLARHEAD/></DECLAR>"
    with pytest.raises(ValueError, match="DECLARBODY"):
        patch_declaration_xml(bad)
