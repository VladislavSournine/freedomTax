"""Extract structured fields from a ДПС letter when user pastes its text.

The input is usually the result of Ctrl+A / Ctrl+C over a scanned PDF, so
spacing is irregular and OCR-style artefacts appear ('Nº'/'Nº'/'N°' for '№',
'Bi'/'B i' for 'Від', letter-spaced cyrillic like 'п р о'). Patterns are
deliberately forgiving — fields that cannot be found are simply omitted from
the returned dict.
"""
from __future__ import annotations

import re

_RNOKPP_RE = re.compile(r"РНОКПП\s+(\d{10})")
_DEKL_RE = re.compile(
    r"від\s+(\d{2}\.\d{2}\.\d{4})\s*N\s*[º°o]\s*(\d{7,12})",
    re.IGNORECASE,
)
_VYKH_DATE_RE = re.compile(
    # Vykh № may contain digits with '-', '/', or even '.' as separators
    # (OCR reads e.g. "07-02" as "07.02"). The separator 'Від' often loses
    # its 'д' ('Bi' in scans). Date's '.' may be misread as ',' — normalize
    # downstream.
    r"(\d[\d\-/.]{6,}[\d])\s+[ВBвb]\s*[іi]\s*[дД]?\s+(\d{2}[.,]\d{2}[.,]\d{4})",
)
_YEAR_RE = re.compile(r"за\s+(?:звітний\s+)?(\d{4})\s*рік")
_ADDR_RE = re.compile(
    r"вул\.\s*[^,\n]+,\s*кв\.\s*\d+[^\n]*?\d{5}",
    re.IGNORECASE,
)
_DATIVE_NAME_RE = re.compile(
    r"^([А-ЯІЇЄҐ]{3,})\s+([А-ЯІЇЄҐ]{3,})(?:\s+([А-ЯІЇЄҐ]{3,}))?$"
)


def parse_dps_letter(text: str) -> dict:
    """Parse DPS letter text. Unknown fields are omitted from returned dict.

    Keys (all optional): rnokpp, tax_year, declaration_num, declaration_date,
    letter_vykh, letter_date, address, pib_nominative.
    """
    if not text or not text.strip():
        return {}

    out: dict = {}

    m = _RNOKPP_RE.search(text)
    if m:
        out["rnokpp"] = m.group(1)

    m = _DEKL_RE.search(text)
    if m:
        out["declaration_date"] = m.group(1)
        out["declaration_num"] = m.group(2)

    m = _VYKH_DATE_RE.search(text)
    if m:
        out["letter_vykh"] = m.group(1).strip()
        # Normalize OCR-flipped separators in date ('16.04,2026' → '16.04.2026')
        out["letter_date"] = m.group(2).replace(",", ".")

    m = _YEAR_RE.search(text)
    if m:
        out["tax_year"] = m.group(1)

    m = _ADDR_RE.search(text)
    if m:
        out["address"] = " ".join(m.group(0).split())

    # Recipient's ПІБ in dative (all-caps cyrillic line, 2–3 words)
    for line in text.splitlines():
        ls = " ".join(line.strip().split())
        dm = _DATIVE_NAME_RE.match(ls)
        if dm:
            parts = [p for p in dm.groups() if p]
            nom = [_dative_to_nominative(p) for p in parts]
            # DPS writes "FIRST [PATRONYMIC] SURNAME".
            # Output in business order: "Surname First [Patronymic]".
            if len(nom) == 2:
                out["pib_nominative"] = f"{nom[1]} {nom[0]}"
            else:
                out["pib_nominative"] = f"{nom[2]} {nom[0]} {nom[1]}"
            break

    return out


_LETTER2_MARKERS: tuple[tuple[str, int], ...] = (
    ("надання документів", 3),
    ("10.10", 3),
    ("межами україни", 2),
    ("ст.78", 2),
    ("ст. 78", 2),
    ("позапланової перевірки", 2),
    ("платіжними", 1),
)
_LETTER1_MARKERS: tuple[tuple[str, int], ...] = (
    ("10.13", 3),
    ("11.3", 2),
    ("звітна нова", 3),
    ("звітної нової", 3),
    ("уточнююч", 2),
    ("ознак", 1),
    ("додаткове благо", 2),
    ("камеральн", 2),
)


def classify_letter(text: str) -> str:
    """Return 'doc_request' (letter #2), 'cameralca' (letter #1) or '' (unknown).

    Uses keyword markers with weights. Ties and zero scores return '' so the
    caller can fall back to user intent rather than guessing.
    """
    if not text:
        return ""
    t = text.lower()
    score_2 = sum(w for kw, w in _LETTER2_MARKERS if kw in t)
    score_1 = sum(w for kw, w in _LETTER1_MARKERS if kw in t)
    if score_2 > score_1:
        return "doc_request"
    if score_1 > score_2:
        return "cameralca"
    return ""


def _dative_to_nominative(word: str) -> str:
    """Naive Ukrainian dative→nominative for all-caps male names.

    Handles the common case: strip trailing 'у'/'ю' if length > 3.
    Misses female endings (-і → -а) and rare declensions — caller should
    allow manual edit in the rendered output.
    """
    w = word.title()
    if len(w) > 3 and w.endswith(("у", "ю")):
        w = w[:-1]
    return w
