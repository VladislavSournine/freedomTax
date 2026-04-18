from io import BytesIO
from textwrap import dedent

from src.drfo_xml import parse_f1419104_xml
from src.tax import aggregate_drfo_oznakas


def _xml(rows: list[tuple[int, str, str, str, str, str]]) -> bytes:
    """Build a minimal F1419104 XML from (rownum, oznaka, G7, G9, G11, G13S_rest) tuples."""
    body_elements = []
    for rn, _, g7, g9, g11, g13s in rows:
        body_elements.append(f'<T1RXXXXG7 ROWNUM="{rn}">{g7}</T1RXXXXG7>')
        body_elements.append(f'<T1RXXXXG9 ROWNUM="{rn}">{g9}</T1RXXXXG9>')
        body_elements.append(f'<T1RXXXXG11 ROWNUM="{rn}">{g11}</T1RXXXXG11>')
        body_elements.append(f'<T1RXXXXG13S ROWNUM="{rn}">{g13s}</T1RXXXXG13S>')
    xml = dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <DECLAR>
          <DECLARHEAD><TIN>0</TIN></DECLARHEAD>
          <DECLARBODY>
            {''.join(body_elements)}
          </DECLARBODY>
        </DECLAR>""").encode("utf-8")
    return xml


def test_parse_aggregates_per_oznaka():
    xml = _xml([
        (1, "126", "106.16", "19.11", "5.31", "126 - Додаткове благо"),
        (2, "101", "287051.62", "14352.58", "14352.58", "101 - Заробiтна плата"),
        (3, "125", "3250.75", "0.00", "0.00", "125 - Пенсiйнi внески"),
        (4, "160", "1721.00", "0.00", "0.00", "160 - Вартiсть дарункiв"),
        (5, "126", "200.56", "36.11", "10.03", "126 - Додаткове благо"),
        (6, "127", "4348.40", "782.71", "217.42", "127 - Iншi доходи"),
        (30, "777", "3750771.29", "1849.90", "0.00", "777 - Податкова декларацiя"),
    ])
    parsed = parse_f1419104_xml(BytesIO(xml))
    assert parsed["oznaka_126_income"] == 306.72      # 106.16 + 200.56
    assert parsed["oznaka_126_pdfo_withheld"] == 55.22
    assert parsed["oznaka_126_vz_withheld"] == 15.34
    assert parsed["oznaka_127_income"] == 4348.40
    assert parsed["oznaka_127_pdfo_withheld"] == 782.71
    assert parsed["oznaka_127_vz_withheld"] == 217.42
    assert parsed["oznaka_125_income"] == 3250.75
    assert parsed["oznaka_160_income"] == 1721.00
    # Ознака 101 (ЗП) — для крос-звірки
    assert parsed["row_101_income"] == 287051.62
    # Ознака 777 (рядок платника) — ігнорується
    assert "oznaka_777_income" not in parsed


def test_parse_empty_xml():
    xml = _xml([])
    parsed = parse_f1419104_xml(BytesIO(xml))
    assert parsed["oznaka_126_income"] == 0.0
    assert parsed["oznaka_127_income"] == 0.0
    assert parsed["oznaka_125_income"] == 0.0
    assert parsed["oznaka_160_income"] == 0.0


def test_parse_feeds_aggregate():
    """Parser output is directly usable as kwargs for aggregate_drfo_oznakas."""
    xml = _xml([
        (1, "126", "1409.52", "253.72", "70.49", "126 - Додаткове благо"),
        (2, "127", "4348.40", "782.71", "217.42", "127 - Iншi доходи"),
        (3, "125", "13166.25", "0", "0", "125 - Пенсiйнi внески"),
        (4, "160", "5133.50", "0", "0", "160 - Вартiсть дарункiв"),
    ])
    parsed = parse_f1419104_xml(BytesIO(xml))
    # Strip cross-check fields that aggregate_drfo_oznakas doesn't accept
    kwargs = {k: v for k, v in parsed.items() if not k.startswith("row_")}
    result = aggregate_drfo_oznakas(**kwargs)
    assert result["row_10_13_income"] == 5757.92
    assert result["row_10_13_pdfo_withheld"] == 1036.43
    assert result["row_10_13_vz_withheld"] == 287.91
    assert result["row_11_3_income"] == 18299.75
