import json
import re
from datetime import date
from typing import Optional

import requests
from flask import Flask, Response, flash, redirect, render_template, request, url_for

from lxml import etree

from src.drfo_xml import parse_f1419104_xml
from src.fifo import (FIFOCalculator, enrich_dividends_with_uah,
                      enrich_other_income_with_uah,
                      enrich_withholding_taxes_with_uah)
from src.letter_parser import classify_letter, parse_dps_letter
from src.letter_text import render_letter_text, suggest_korotky_zmist
from src.nbu import NBUClient
from src.parser import parse_freedom_json
from src.pdf_export import letter_to_pdf, merge_pdfs
from src.tax import aggregate_drfo_oznakas, calculate_taxes
from src.xml_patcher import patch_declaration_xml

app = Flask(__name__)
app.secret_key = "local-tax-calculator-dev-secret"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

@app.template_filter("enumerate")
def _enumerate_filter(iterable, start=0):
    return enumerate(iterable, start=start)

_CURRENT_YEAR = date.today().year
YEAR_OPTIONS = list(range(_CURRENT_YEAR, 2019, -1))  # e.g. [2026, 2025, ..., 2020]
DEFAULT_YEAR = _CURRENT_YEAR - 1


@app.route("/")
def upload():
    return render_template("upload.html", years=YEAR_OPTIONS, default_year=DEFAULT_YEAR)


@app.route("/calculate", methods=["POST"])
def calculate():
    # --- validate file ---
    f = request.files.get("file")
    if not f or f.filename == "":
        flash("Оберіть файл для завантаження")
        return redirect(url_for("upload"))

    try:
        raw = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        flash("Невірний формат файлу. Завантажте JSON звіт з Freedom24")
        return redirect(url_for("upload"))

    # --- validate year ---
    try:
        tax_year = int(request.form.get("tax_year", 0))
        if not (2020 <= tax_year <= _CURRENT_YEAR):
            raise ValueError
    except (ValueError, TypeError):
        flash("Невірний звітний рік")
        return redirect(url_for("upload"))

    # --- parse Freedom24 structure ---
    try:
        parsed = parse_freedom_json(raw)
    except (KeyError, TypeError, AttributeError, ValueError, IndexError):
        flash("Файл не схожий на звіт Freedom24. Перевірте що обрали правильний файл")
        return redirect(url_for("upload"))

    # --- NBU rates + FIFO ---
    try:
        nbu = NBUClient()
        positions = FIFOCalculator(nbu).calculate(parsed["trades"], tax_year)
        dividends = enrich_dividends_with_uah(parsed["dividends"], nbu)
        other_income = enrich_other_income_with_uah(parsed["other_income"], nbu)
        withholding_taxes = enrich_withholding_taxes_with_uah(
            parsed["withholding_taxes"], nbu
        )
    except requests.RequestException:
        flash("Не вдалося отримати курси НБУ. Перевірте інтернет-з'єднання")
        return redirect(url_for("upload"))
    except RuntimeError as e:
        flash(f"Помилка курсів НБУ: {e}")
        return redirect(url_for("upload"))

    # --- filter by tax year ---
    dividends_year = [d for d in dividends if d["date"][:4] == str(tax_year)]
    other_income_year = [i for i in other_income if i["date"][:4] == str(tax_year)]
    wht_year = [t for t in withholding_taxes if t["date"][:4] == str(tax_year)]

    # --- calculate taxes ---
    tax_result = calculate_taxes(
        positions,
        dividends_year,
        tax_year,
        other_income=other_income_year,
        withholding_taxes=wht_year,
    )

    # --- F1419104 (довідка з ДРФО): prefer XML upload, fall back to manual form ---
    drfo_kwargs, drfo_source, row_101_crosscheck = _extract_drfo_inputs(request)
    drfo = aggregate_drfo_oznakas(**drfo_kwargs)
    drfo["source"] = drfo_source
    drfo["row_101_income"] = row_101_crosscheck

    # --- group positions by ticker for F1 table ---
    f1_groups = _group_by_ticker(positions)

    # --- cover-letter autofill ---
    # Letter #2 (document request for row 10.10) drives the letter header.
    # Letter #1 (камералка — про ряд. 10.13/11.3) feeds point 4.
    letter2_text = request.form.get("dps_letter_text", "")
    letter1_text = request.form.get("letter1_text", "")
    # Detect a swap — if user pasted them into the wrong fields, swap silently
    # and flag a warning. If the content is ambiguous, only warn.
    kind2, kind1 = classify_letter(letter2_text), classify_letter(letter1_text)
    if kind2 == "cameralca" and kind1 == "doc_request":
        flash("Схоже, тексти двох листів переплутано місцями — автоматично міняю їх. "
              "Перевір шапку супровідного листа і пункт 4 нижче.")
        letter2_text, letter1_text = letter1_text, letter2_text
    elif (kind2 == "cameralca" and letter2_text) or (kind1 == "doc_request" and letter1_text):
        flash("Схоже, один із текстів листа ДПС не відповідає своєму полю. "
              "Перевір, що в полі «Лист №2» — саме запит документів (про ряд. 10.10), "
              "а в «Лист №1» — камералка (про ряд. 10.13/11.3).")

    letter_ctx = parse_dps_letter(letter2_text)
    letter_ctx["contact_email"] = (request.form.get("contact_email") or "").strip()
    letter_ctx["contact_phone"] = (request.form.get("contact_phone") or "").strip()
    # Freedom24 account № from filename prefix (e.g. "NNNNNNN_...json" → "NNNNNNN")
    fname_match = re.match(r"(\d+)_", f.filename or "")
    letter_ctx["freedom24_account"] = fname_match.group(1) if fname_match else ""
    # Letter #1 — only вих. № + date are needed for point 4. Reuse the parser.
    letter1_parsed = parse_dps_letter(letter1_text)
    letter_ctx["letter1_vykh"] = letter1_parsed.get("letter_vykh", "")
    letter_ctx["letter1_date"] = letter1_parsed.get("letter_date", "")

    # Manual overrides for вих. № / date. The parser's input is Ctrl+C'd from
    # a ДПС PDF, where Cyrillic glyphs (esp. Ж, ї, і) are often mis-encoded —
    # e.g. "19956/Ж12/26-15-24-…" pastes as "1995671226-15-24-…". Cabinet's
    # «Вхідні документи» list shows the same index as plain text, so giving
    # the user a clean text input to paste from there is the reliable fix.
    for parsed_key, form_key in (
        ("letter_vykh", "letter_vykh_manual"),
        ("letter_date", "letter_date_manual"),
        ("letter1_vykh", "letter1_vykh_manual"),
        ("letter1_date", "letter1_date_manual"),
    ):
        override = (request.form.get(form_key) or "").strip()
        if override:
            letter_ctx[parsed_key] = override
    # Звітна нова reg. № + date — cannot be parsed (filed by the taxpayer).
    letter_ctx["zvit_nova_num"] = (request.form.get("zvit_nova_num") or "").strip()
    letter_ctx["zvit_nova_date"] = (request.form.get("zvit_nova_date") or "").strip()

    letter_totals = {
        "letter_total": tax_result["dividend_income_uah"] + tax_result["other_income_uah"],
        "letter_pdfo": tax_result["pdfo_dividends"] + tax_result["pdfo_other"],
        "letter_vz": tax_result["vz_dividends"] + tax_result["vz_other"],
    }

    return render_template(
        "result.html",
        tax_result=tax_result,
        drfo=drfo,
        f1_groups=f1_groups,
        tax_year=tax_year,
        has_trades=bool(f1_groups),
        letter_ctx=letter_ctx,
        letter_text=render_letter_text(letter_ctx, tax_year, letter_totals),
        letter_totals=letter_totals,
        korotky_zmist=suggest_korotky_zmist(letter_ctx, tax_year),
    )


@app.route("/patch-xml", methods=["POST"])
def patch_xml():
    """Inject Freedom24 row 10.10 (and optionally 10.8) into a user's draft
    F0100215 XML and return the patched XML as a download."""
    xml_file = request.files.get("xml")
    if not xml_file or not xml_file.filename:
        flash("Оберіть XML-файл чернетки декларації (завантаж із ЕК перед подачею)")
        return redirect(url_for("upload"))
    try:
        patched = patch_declaration_xml(
            xml_file.read(),
            foreign_income=_parse_amount(request.form.get("foreign_income")),
            pdfo_foreign=_parse_amount(request.form.get("pdfo_foreign")),
            vz_foreign=_parse_amount(request.form.get("vz_foreign")),
            trades_profit=_parse_amount(request.form.get("trades_profit")),
            pdfo_trades=_parse_amount(request.form.get("pdfo_trades")),
            vz_trades=_parse_amount(request.form.get("vz_trades")),
            row_10_13_income=_parse_amount(request.form.get("row_10_13_income")),
            row_10_13_pdfo=_parse_amount(request.form.get("row_10_13_pdfo")),
            row_10_13_vz=_parse_amount(request.form.get("row_10_13_vz")),
            row_11_3_income=_parse_amount(request.form.get("row_11_3_income")),
        )
    except etree.XMLSyntaxError as e:
        flash(f"XML чернетки пошкоджений: {e}")
        return redirect(url_for("upload"))
    except ValueError as e:
        flash(f"Не схоже на F0100215: {e}")
        return redirect(url_for("upload"))
    return Response(
        patched,
        mimetype="application/xml",
        headers={
            "Content-Disposition": 'attachment; filename="F0100215_patched.xml"'
        },
    )


@app.route("/export-cabinet-pdf", methods=["POST"])
def export_cabinet_pdf():
    """Build the single PDF that ЕК «Листування з ДПС» expects: cover letter
    on page 1, Freedom24 PDF report below, optionally F1419104 PDF at the end.

    All letter context is re-submitted as hidden form fields (this endpoint
    is stateless — it doesn't re-parse the user's Freedom24 JSON)."""
    freedom24_pdf = request.files.get("freedom24_pdf")
    if not freedom24_pdf or not freedom24_pdf.filename:
        flash("Завантаж PDF-звіт Freedom24 — без нього об'єднаний файл зібрати не можу")
        return redirect(url_for("upload"))
    f1419104_pdf = request.files.get("f1419104_pdf")
    has_drfo_pdf = bool(f1419104_pdf and f1419104_pdf.filename)

    try:
        tax_year = int(request.form.get("tax_year", "0"))
    except ValueError:
        tax_year = 0

    letter_ctx = {
        "pib_nominative": request.form.get("pib_nominative", ""),
        "rnokpp": request.form.get("rnokpp", ""),
        "address": request.form.get("address", ""),
        "contact_email": request.form.get("contact_email", ""),
        "contact_phone": request.form.get("contact_phone", ""),
        "letter_vykh": request.form.get("letter_vykh", ""),
        "letter_date": request.form.get("letter_date", ""),
        "declaration_num": request.form.get("declaration_num", ""),
        "declaration_date": request.form.get("declaration_date", ""),
        "freedom24_account": request.form.get("freedom24_account", ""),
        "letter1_vykh": request.form.get("letter1_vykh", ""),
        "letter1_date": request.form.get("letter1_date", ""),
        "zvit_nova_num": request.form.get("zvit_nova_num", ""),
        "zvit_nova_date": request.form.get("zvit_nova_date", ""),
    }
    totals = {
        "letter_total": _parse_amount(request.form.get("letter_total")),
        "letter_pdfo": _parse_amount(request.form.get("letter_pdfo")),
        "letter_vz": _parse_amount(request.form.get("letter_vz")),
    }

    letter_text = render_letter_text(letter_ctx, tax_year, totals, has_drfo_pdf)
    try:
        letter_pdf_bytes = letter_to_pdf(letter_text)
    except Exception as e:
        flash(f"Не вдалося згенерувати PDF листа: {e}")
        return redirect(url_for("upload"))

    parts = [letter_pdf_bytes, freedom24_pdf.read()]
    if has_drfo_pdf:
        parts.append(f1419104_pdf.read())
    try:
        merged = merge_pdfs(parts)
    except Exception as e:
        flash(f"Не вдалося об'єднати PDF-файли: {e}")
        return redirect(url_for("upload"))

    filename = f"Vidpovid_DPS_{tax_year or 'N'}.pdf"
    return Response(
        merged,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _parse_amount(raw: Optional[str]) -> float:
    """Accept Ukrainian-style decimals ('1 409,52') and plain floats; empty → 0."""
    if not raw:
        return 0.0
    cleaned = raw.replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        return max(0.0, float(cleaned))
    except ValueError:
        return 0.0


_DRFO_KW = (
    "oznaka_126_income", "oznaka_126_pdfo_withheld", "oznaka_126_vz_withheld",
    "oznaka_127_income", "oznaka_127_pdfo_withheld", "oznaka_127_vz_withheld",
    "oznaka_125_income", "oznaka_160_income",
)


def _extract_drfo_inputs(req) -> tuple[dict, str, float]:
    """Return (kwargs for aggregate_drfo_oznakas, source label, row_101 cross-check)."""
    xml_file = req.files.get("drfo_xml")
    if xml_file and xml_file.filename:
        try:
            parsed = parse_f1419104_xml(xml_file.stream)
            kwargs = {k: parsed[k] for k in _DRFO_KW}
            return kwargs, "xml", parsed.get("row_101_income", 0.0)
        except (etree.XMLSyntaxError, ValueError, KeyError):
            flash("Не вдалося розпарсити XML довідки F1419104 — використовую цифри з форми")
    # manual form fallback — short-name keys in HTML form → full kwarg names
    form_map = {
        "oznaka_126_income": "oznaka_126_income",
        "oznaka_126_pdfo_withheld": "oznaka_126_pdfo",
        "oznaka_126_vz_withheld": "oznaka_126_vz",
        "oznaka_127_income": "oznaka_127_income",
        "oznaka_127_pdfo_withheld": "oznaka_127_pdfo",
        "oznaka_127_vz_withheld": "oznaka_127_vz",
        "oznaka_125_income": "oznaka_125_income",
        "oznaka_160_income": "oznaka_160_income",
    }
    kwargs = {kw: _parse_amount(req.form.get(field)) for kw, field in form_map.items()}
    return kwargs, "manual", 0.0


def _group_by_ticker(positions: list) -> list:
    groups: dict = {}
    for pos in positions:
        t = pos["ticker"]
        if t not in groups:
            groups[t] = {"ticker": t, "proceeds_uah": 0.0,
                         "expenses_uah": 0.0, "profit_uah": 0.0}
        groups[t]["proceeds_uah"] += pos["proceeds_uah"]
        groups[t]["expenses_uah"] += (
            pos["cost_uah"] + pos["buy_commission_uah"] + pos["sell_commission_uah"]
        )
        groups[t]["profit_uah"] += pos["profit_uah"]
    return list(groups.values())


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, port=port)
