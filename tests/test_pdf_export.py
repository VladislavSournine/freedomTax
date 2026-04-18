"""Tests for src.pdf_export.

letter_to_pdf is a thin wrapper over fpdf2 — the things actually worth guarding:
1. Produces real PDF bytes (header magic).
2. Survives Cyrillic input (Arial.ttf must be found; otherwise the user silently
   gets missing-glyph boxes in the cabinet).
3. Does not crash on an unbreakable token wider than the page (wrapmode="CHAR"
   guarantee — the regression we just fixed).

merge_pdfs: order is preserved, empty input is rejected, page count adds up.
"""
from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from src.pdf_export import letter_to_pdf, merge_pdfs


def test_letter_to_pdf_returns_pdf_magic():
    pdf = letter_to_pdf("Привіт, світ.\nРядок 2.")
    assert pdf[:4] == b"%PDF"
    # fpdf2 emits %%EOF at the end (possibly followed by a newline)
    assert b"%%EOF" in pdf[-32:]


def test_letter_to_pdf_renders_cyrillic_single_page():
    text = "ПОЯСНЕННЯ\nдо запиту щодо рядка 10.10 декларації за 2025 рік"
    pdf = letter_to_pdf(text)
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) >= 1


def test_letter_to_pdf_handles_long_unbreakable_token():
    """Regression: a token longer than the page width used to raise
    FPDFException('Not enough horizontal space…'). wrapmode='CHAR' must
    allow fpdf2 to break inside the token."""
    huge_token = "A" * 400  # no spaces — single unbreakable "word"
    text = f"Посилання: {huge_token}\nІнший рядок."
    pdf = letter_to_pdf(text)  # must not raise
    assert pdf[:4] == b"%PDF"


def test_letter_to_pdf_handles_empty_lines():
    """Empty lines in the source text must still produce a vertical gap
    (we feed them as a single space to keep multi_cell happy)."""
    text = "Рядок 1\n\nРядок після пропуску"
    pdf = letter_to_pdf(text)
    assert pdf[:4] == b"%PDF"


def test_merge_pdfs_concatenates_pages():
    a = letter_to_pdf("one")
    b = letter_to_pdf("two")
    merged = merge_pdfs([a, b])
    pages_a = len(PdfReader(io.BytesIO(a)).pages)
    pages_b = len(PdfReader(io.BytesIO(b)).pages)
    pages_m = len(PdfReader(io.BytesIO(merged)).pages)
    assert pages_m == pages_a + pages_b


def test_merge_pdfs_preserves_order():
    """The order of input blobs must be the order of output pages — cover
    letter first, Freedom24 report second, F1419104 last (the cabinet flow
    depends on this)."""
    first = letter_to_pdf("FIRST_MARKER")
    second = letter_to_pdf("SECOND_MARKER")
    merged = merge_pdfs([first, second])
    reader = PdfReader(io.BytesIO(merged))
    page1_text = reader.pages[0].extract_text() or ""
    # First page must come from `first`, not `second`.
    assert "FIRST_MARKER" in page1_text


def test_merge_pdfs_rejects_empty_list():
    with pytest.raises(ValueError):
        merge_pdfs([])


def test_merge_pdfs_single_blob_round_trips():
    a = letter_to_pdf("solo")
    merged = merge_pdfs([a])
    assert len(PdfReader(io.BytesIO(merged)).pages) == len(
        PdfReader(io.BytesIO(a)).pages
    )
