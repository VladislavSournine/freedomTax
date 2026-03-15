import json
from datetime import date

import requests
from flask import Flask, flash, redirect, render_template, request, url_for

from src.fifo import (FIFOCalculator, enrich_dividends_with_uah,
                      enrich_other_income_with_uah,
                      enrich_withholding_taxes_with_uah)
from src.nbu import NBUClient
from src.parser import parse_freedom_json
from src.tax import calculate_taxes

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

    # --- group positions by ticker for F1 table ---
    f1_groups = _group_by_ticker(positions)

    return render_template(
        "result.html",
        tax_result=tax_result,
        f1_groups=f1_groups,
        tax_year=tax_year,
        has_trades=bool(f1_groups),
    )


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
