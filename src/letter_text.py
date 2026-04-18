"""Render the cover letter (response to ДПС inquiry about row 10.10) as plain text.

Single source of truth for both (a) the <pre id="coverLetter"> block on the
result page and (b) the PDF version that ships inside the merged cabinet file.

Kept ADDRESSEE-less by design — when the letter is delivered through
cabinet.tax.gov.ua "Листування з ДПС", the routing is driven by the form's
own Код ДПІ + підрозділ dropdowns, and repeating "Головне управління ДПС..."
inside the letter body is just redundant paper-mail convention.
"""
from __future__ import annotations

from datetime import date


def _fld(value: str | None, placeholder: str) -> str:
    """Return value if truthy, else «placeholder» in guillemets.

    Guillemets act as an easy-to-spot marker in plain text — the result page
    highlights them in yellow via JS, and in PDF they read as obvious gaps.
    """
    v = (value or "").strip()
    return v if v else f"«{placeholder}»"


def render_letter_text(
    letter_ctx: dict,
    tax_year: int,
    totals: dict,
    has_f1419104_pdf: bool = False,
    today: date | None = None,
) -> str:
    """Build the plain-text cover letter.

    totals keys: letter_total, letter_pdfo, letter_vz (all floats, UAH).
    has_f1419104_pdf: if True, the letter references F1419104 as part of the
    merged PDF's contents; otherwise that bullet is omitted.
    today: the signing date stamped at the bottom of the letter; defaults to
    the system date (the letter is always dated when it is generated).
    """
    next_year = tax_year + 1
    today_str = (today or date.today()).strftime("%d.%m.%Y")
    vykh = _fld(letter_ctx.get("letter_vykh"), "№_______")
    vykh_date = _fld(letter_ctx.get("letter_date"), f"__.__.{next_year}")
    decl_num = _fld(letter_ctx.get("declaration_num"), "№_______")
    decl_date = _fld(letter_ctx.get("declaration_date"), f"__.__.{next_year}")
    acc_num = _fld(letter_ctx.get("freedom24_account"), "номер рахунку")
    l1_vykh = _fld(letter_ctx.get("letter1_vykh"), "№_______")
    l1_date = _fld(letter_ctx.get("letter1_date"), f"__.__.{next_year}")
    zvit_num = _fld(letter_ctx.get("zvit_nova_num"), "№_______")
    zvit_date = _fld(letter_ctx.get("zvit_nova_date"), f"__.__.{next_year}")
    pib = _fld(letter_ctx.get("pib_nominative"), "ПІБ платника")
    pib_sign = _fld(letter_ctx.get("pib_nominative"), "ПІБ")

    t_total = f"{totals['letter_total']:.2f}"
    t_pdfo = f"{totals['letter_pdfo']:.2f}"
    t_vz = f"{totals['letter_vz']:.2f}"

    f1419104_line = (
        "   - Довідка з ДРФО (F1419104) за "
        f"{tax_year} рік — підтвердження сум ряд. 10.13 / 11.3.\n"
        if has_f1419104_pdf
        else ""
    )

    return f"""Від: {pib}
РНОКПП: {_fld(letter_ctx.get("rnokpp"), "10 цифр")}
Адреса: {_fld(letter_ctx.get("address"), "адреса реєстрації")}
Email: {_fld(letter_ctx.get("contact_email"), "контактний email")}
Тел.: {_fld(letter_ctx.get("contact_phone"), "контактний телефон")}

ПОЯСНЕННЯ
до запиту вих. {vykh} від {vykh_date}
щодо рядка 10.10 податкової декларації про майновий стан і доходи
за {tax_year} рік (реєстраційний {decl_num} від {decl_date})

У відповідь на Ваш запит щодо підтвердження сум, зазначених у рядку 10.10
декларації, повідомляю наступне.

1. Джерело доходу: брокерський рахунок у Freedom Finance Europe Ltd
   (Freedom24), клієнтський номер {acc_num}. У {tax_year} році отримано
   пасивні іноземні доходи (дивіденди по американських акціях та
   нарахування за програмою лояльності/cashback) у сумі {t_total} грн
   у еквіваленті.

2. Розрахунок виконано самостійно за курсами НБУ на дату отримання кожного
   доходу. Ставки: ПДФО 18% (з урахуванням зарахування іноземного WHT 15%
   у межах 9% — п. 170.11 ПКУ), ВЗ 5% (з 01.01.2025 — Закон №4015).
   Отримані суми:
     - сума доходу: {t_total} грн;
     - ПДФО:        {t_pdfo} грн;
     - ВЗ:          {t_vz} грн.

   Зобов'язання з ПДФО та ВЗ буде сплачено у встановлений строк —
   до 01.08.{next_year} (п. 179.7 ст. 179 ПКУ).

3. Документальне підтвердження наведено у складі цього ж файлу:
   - Звіт брокера Freedom24 за {tax_year} рік у форматі PDF (нижче у цьому
     документі). У ньому розділ «Cash Flows» містить усі виплати:
     дивіденди, cashback/лояльність та утриманий у джерелі податок
     US WHT 15% — це першоджерело цифр з п. 2 вище. Розділ «Trades» —
     операції купівлі/продажу акцій (якщо застосовно до ряд. 10.8 / Ф1).
{f1419104_line}
   Оригінальний звіт у форматі JSON можу надати додатково на запит.

4. Одночасно повідомляю, що у відповідь на лист ДПС вих. {l1_vykh} від
   {l1_date} подано "Звітну нову" декларацію з коригуванням рядків 10.13 і
   11.3 (реєстраційний {zvit_num} від {zvit_date}).

Дата: {today_str}                            Підпис (КЕП): {pib_sign}
"""


def suggest_korotky_zmist(letter_ctx: dict, tax_year: int, max_len: int = 100) -> str:
    """Suggest a <100-char value for the ЕК 'Короткий зміст' field."""
    vykh = (letter_ctx.get("letter_vykh") or "").strip() or "[№ запиту]"
    vykh_date = (letter_ctx.get("letter_date") or "").strip() or "[дата]"
    base = f"Відповідь на запит {vykh} від {vykh_date} щодо ряд. 10.10 декларації за {tax_year}"
    if len(base) <= max_len:
        return base
    # Fall back to a tighter template that always fits when vykh is unusually long.
    return f"Відповідь на запит {vykh} щодо ряд. 10.10 декларації за {tax_year}"[:max_len]
