"""Tests for src.letter_text.

The cover letter has two load-bearing behaviors:
1. Empty user fields must render as «…»-wrapped placeholders so that (a) the
   result page highlights them in yellow and (b) the PDF reader can spot gaps.
2. The text narrative changes shape based on has_f1419104_pdf (one extra
   bullet in the "documents attached below" section).

suggest_korotky_zmist has a hard 100-char cap imposed by the cabinet form.
"""
from __future__ import annotations

from datetime import date

from src.letter_text import render_letter_text, suggest_korotky_zmist

_FULL_CTX = {
    "letter_vykh": "19956/Ж12/26-15-24-01-02-12",
    "letter_date": "16.04.2026",
    "declaration_num": "9999999999",
    "declaration_date": "01.04.2026",
    "freedom24_account": "F24-12345",
    "letter1_vykh": "123/Ж10/26-15-24",
    "letter1_date": "10.03.2026",
    "zvit_nova_num": "8888888888",
    "zvit_nova_date": "20.04.2026",
    "pib_nominative": "Сурнін Владислав Олександрович",
    "rnokpp": "1234567890",
    "address": "м. Київ, вул. Приклад, 1, кв. 1",
    "contact_email": "test@example.com",
    "contact_phone": "+380991234567",
}
_TOTALS = {"letter_total": 15000.50, "letter_pdfo": 1350.05, "letter_vz": 750.03}


def test_render_letter_has_no_dps_address_header():
    """Cabinet routes by form dropdowns — a 'Головне управління ДПС…' header
    in the letter body would be redundant and risks conflicting with routing."""
    text = render_letter_text(_FULL_CTX, 2025, _TOTALS)
    assert "Головне управління" not in text
    assert "ДПС у" not in text


def test_render_letter_uses_single_file_wording():
    text = render_letter_text(_FULL_CTX, 2025, _TOTALS)
    assert "у складі цього ж файлу" in text
    assert "додатках" not in text  # old multi-file wording must be gone


def test_render_letter_empty_fields_become_guillemet_placeholders():
    """A missing field must appear as «…» so the result-page JS highlighter
    (which matches /«[^»]+»/g) can flag it."""
    ctx = {k: "" for k in _FULL_CTX}
    text = render_letter_text(ctx, 2025, _TOTALS)
    assert "«ПІБ платника»" in text
    assert "«10 цифр»" in text
    assert "«№_______»" in text
    assert "«адреса реєстрації»" in text


def test_render_letter_includes_totals_with_two_decimals():
    text = render_letter_text(_FULL_CTX, 2025, _TOTALS)
    assert "15000.50 грн" in text
    assert "1350.05 грн" in text
    assert "750.03 грн" in text


def test_render_letter_f1419104_line_appears_only_when_flagged():
    without = render_letter_text(_FULL_CTX, 2025, _TOTALS, has_f1419104_pdf=False)
    with_ = render_letter_text(_FULL_CTX, 2025, _TOTALS, has_f1419104_pdf=True)
    assert "F1419104" not in without
    assert "F1419104" in with_
    # The conditional bullet must slot inside point 3 (documents) and not
    # before point 2 — simple proximity check.
    assert with_.index("F1419104") > with_.index("Документальне підтвердження")
    assert with_.index("F1419104") < with_.index("Оригінальний звіт")


def test_render_letter_payment_deadline_uses_next_year():
    text = render_letter_text(_FULL_CTX, 2025, _TOTALS)
    assert "01.08.2026" in text  # п. 179.7 deadline = Aug 1 of filing year


def test_render_letter_signing_date_stamps_today():
    """The «Дата:» line at the bottom must carry the signing date (today),
    formatted DD.MM.YYYY. The old «__.__.YYYY» placeholder must be gone."""
    text = render_letter_text(_FULL_CTX, 2025, _TOTALS, today=date(2026, 4, 17))
    assert "Дата: 17.04.2026" in text
    assert "__.__." not in text


def test_render_letter_signing_date_defaults_to_today():
    """No today= argument → system date used. We only check the format to
    avoid flakiness when the test runs across midnight."""
    text = render_letter_text(_FULL_CTX, 2025, _TOTALS)
    import re
    assert re.search(r"Дата: \d{2}\.\d{2}\.\d{4}", text) is not None


def test_suggest_korotky_zmist_under_100_chars_for_typical_input():
    s = suggest_korotky_zmist(_FULL_CTX, 2025)
    assert len(s) <= 100
    assert "19956/Ж12" in s
    assert "2025" in s


def test_suggest_korotky_zmist_falls_back_when_base_too_long():
    """If вих. + date alone push past 100 chars, the template must drop the
    date (fallback template), and the result must still be capped at 100."""
    ctx = dict(_FULL_CTX)
    ctx["letter_vykh"] = "X" * 120  # force overflow
    s = suggest_korotky_zmist(ctx, 2025)
    assert len(s) <= 100


def test_suggest_korotky_zmist_handles_empty_vykh():
    """Missing input must not crash — the cabinet field is still populated,
    just with a visible placeholder the user can edit."""
    ctx = {k: "" for k in _FULL_CTX}
    s = suggest_korotky_zmist(ctx, 2025)
    assert len(s) <= 100
    assert "[№ запиту]" in s or "ряд. 10.10" in s
