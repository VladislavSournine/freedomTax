from src.letter_parser import classify_letter, parse_dps_letter

# Real sample — Ctrl+A from scanned DPS PDF, preserves OCR artefacts
# ('Nº', 'Bi', letter-spaced words, footer inlined mid-document).
SAMPLE = """ДЕРЖАВНА ПОДАТКОВА СЛУЖБА УКРАЇНИ
ГОЛОВНЕ УПРАВЛІННЯ ДПС у м. Києві
вул. Шолуденка, 33/19, м. Київ, 04116, тел.: (044) 454-70-87

ВЛАДИСЛАВУ СУРНІНУ
РНОКПП 2745810755
вул. Дмитрівська 37Б, кв. 14, м.Київ, 02205

Про надання документів щодо декларації
про майновий стан і доходи за 2025 рік

Головне управління ДПС у м. Києві розглянуло подану Вами декларацію
п р о майновий стан і доходи за звітний 2025 рік від 27.03.2026 Nº 9439017433 т а
повідомляє.

1995671226-16-24-01-02-12 Bi 16.04.2026
"""


def test_parse_extracts_all_fields():
    out = parse_dps_letter(SAMPLE)
    assert out["rnokpp"] == "2745810755"
    assert out["tax_year"] == "2025"
    assert out["declaration_num"] == "9439017433"
    assert out["declaration_date"] == "27.03.2026"
    assert out["letter_date"] == "16.04.2026"
    assert out["letter_vykh"].startswith("1995671226")
    assert "Дмитрівська" in out["address"]
    assert "02205" in out["address"]
    assert out["pib_nominative"] == "Сурнін Владислав"


def test_parse_empty():
    assert parse_dps_letter("") == {}
    assert parse_dps_letter("   \n   ") == {}


def test_parse_partial():
    """Missing fields should be omitted, not crash."""
    text = "Якийсь довільний текст без структури"
    out = parse_dps_letter(text)
    assert out == {}


def test_parse_only_rnokpp():
    out = parse_dps_letter("текст РНОКПП 1234567890 ще текст")
    assert out == {"rnokpp": "1234567890"}


def test_parse_three_part_name():
    text = "ВЛАДИСЛАВУ ЮРІЙОВИЧУ СУРНІНУ\nРНОКПП 2745810755"
    out = parse_dps_letter(text)
    # First word = firstname, last = surname, middle = patronymic
    assert out["pib_nominative"] == "Сурнін Владислав Юрійович"


# --- classify_letter ---

LETTER_2_SAMPLE = """Про надання документів щодо декларації
підтвердити документами достовірність відомостей
ряд.10.10 Доходи, отримані з джерел за межами України
відповідно до ст.78 Кодексу
"""

LETTER_1_SAMPLE = """про виявлення порушень у декларації за 2025 рік
не задекларовано доходи за ознаками 126 (Додаткове благо) і 127
рядки 10.13 та 11.3 декларації
пропонується подати Звітну нову до 01.05.2026
"""


def test_classify_doc_request():
    assert classify_letter(LETTER_2_SAMPLE) == "doc_request"


def test_classify_cameralca():
    assert classify_letter(LETTER_1_SAMPLE) == "cameralca"


def test_classify_empty_or_unknown():
    assert classify_letter("") == ""
    assert classify_letter("привіт, це не лист від ДПС") == ""


def test_classify_ignores_mere_case():
    assert classify_letter(LETTER_2_SAMPLE.upper()) == "doc_request"
    assert classify_letter(LETTER_1_SAMPLE.upper()) == "cameralca"


# --- regressions: real OCR footers with noisy separators ---

def test_parse_letter1_cameralca_real_ocr():
    """Letter #1 footer has a dot inside vykh and a comma as date separator."""
    text = "34716/26-15-24-07.02-12 від 16.04,2026"
    out = parse_dps_letter(text)
    assert out["letter_vykh"] == "34716/26-15-24-07.02-12"
    assert out["letter_date"] == "16.04.2026"  # comma normalized to dot


def test_parse_letter2_doc_request_real_ocr():
    """Letter #2 footer has 'Bi' (OCR of 'Від' without 'д')."""
    text = "1995671226-16-24-01-02-12 Bi 16.04.2026"
    out = parse_dps_letter(text)
    assert out["letter_vykh"] == "1995671226-16-24-01-02-12"
    assert out["letter_date"] == "16.04.2026"
