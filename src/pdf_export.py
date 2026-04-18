"""Generate a PDF from the cover-letter text and merge it with user-provided
PDFs (Freedom24 report, optionally F1419104) into a single file for ЕК.

ЕК «Листування з ДПС» accepts exactly one PDF ≤ 5 МБ per message, so we
produce ONE file: cover letter on top, supporting documents below.
"""
from __future__ import annotations

import io
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import WrapMode
from pypdf import PdfReader, PdfWriter

# macOS system fonts. Arial carries full Cyrillic — no need to bundle a TTF.
# If the Mac's Arial were ever missing, FPDF would raise at add_font time;
# that's fine — better than silently falling back to a Latin-only font.
_FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
_FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
_FONT_ITALIC = "/System/Library/Fonts/Supplemental/Arial Italic.ttf"


def letter_to_pdf(text: str) -> bytes:
    """Render plain-text letter into an A4 PDF with Cyrillic support.

    Whitespace and line breaks are preserved (the letter is already formatted
    with column alignment — см. suffix of числа). 10pt monospace-ish look is
    avoided; plain Arial reads better for a formal letter.
    """
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    if Path(_FONT_REG).exists():
        pdf.add_font("Arial", "", _FONT_REG)
    if Path(_FONT_BOLD).exists():
        pdf.add_font("Arial", "B", _FONT_BOLD)
    if Path(_FONT_ITALIC).exists():
        pdf.add_font("Arial", "I", _FONT_ITALIC)
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_font("Arial", size=11)
    # multi_cell with w=pdf.epw anchors the wrap width to the printable area;
    # w=0 (fpdf2 default "remaining from current x") can underflow to 0 when
    # x drifts, which trips "Not enough horizontal space…". new_x/new_y keep
    # the caret at the left margin on the next line so subsequent lines keep
    # full width.
    for line in text.splitlines():
        pdf.set_x(pdf.l_margin)
        # wrapmode="CHAR" lets fpdf2 break mid-token when a single word is
        # wider than the page (e.g. a long вих. number or pasted URL) —
        # prevents the "Not enough horizontal space" crash at the cost of
        # occasionally ugly wraps inside tokens. Fine for a plain-text letter.
        pdf.multi_cell(
            w=pdf.epw,
            h=5.5,
            text=line if line else " ",
            new_x="LMARGIN",
            new_y="NEXT",
            wrapmode=WrapMode.CHAR,
        )
    # fpdf2 returns bytearray — coerce for mimetype correctness downstream.
    return bytes(pdf.output())


def merge_pdfs(pdf_blobs: list[bytes]) -> bytes:
    """Concatenate PDF blobs in order into a single PDF.

    Raises ValueError if any blob contributes zero pages — pypdf silently
    tolerates malformed headers (e.g. a text file renamed to .pdf), and a
    lenient merge would produce a file that's missing the user's attachment
    without any indication. Better to fail loud at the system boundary.
    """
    if not pdf_blobs:
        raise ValueError("no PDFs to merge")
    writer = PdfWriter()
    for idx, blob in enumerate(pdf_blobs):
        reader = PdfReader(io.BytesIO(blob))
        pages_before = len(writer.pages)
        for page in reader.pages:
            writer.add_page(page)
        if len(writer.pages) == pages_before:
            raise ValueError(f"PDF #{idx + 1} has no pages (likely not a valid PDF)")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
