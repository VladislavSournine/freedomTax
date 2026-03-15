from src.report import generate_instruction, generate_f1_table


def _make_tax_result(**overrides):
    base = {
        "net_profit_uah": 0.0,
        "gross_profit_uah": 0.0,
        "dividend_income_uah": 0.0,
        "other_income_uah": 0.0,
        "wht_credit_uah": 0.0,
        "pdfo_total": 0.0,
        "pdfo_trades": 0.0,
        "pdfo_dividends": 0.0,
        "pdfo_other": 0.0,
        "vz_total": 0.0,
        "vz_trades": 0.0,
        "vz_dividends": 0.0,
        "vz_other": 0.0,
    }
    base.update(overrides)
    return base


def test_instruction_contains_key_amounts():
    tax_result = _make_tax_result(
        net_profit_uah=15000.0,
        gross_profit_uah=15000.0,
        dividend_income_uah=500.0,
        pdfo_total=2790.0,
        pdfo_trades=2700.0,
        pdfo_dividends=90.0,
        vz_total=775.0,
        vz_trades=750.0,
        vz_dividends=25.0,
    )
    text = generate_instruction(tax_result, tax_year=2024)
    assert "15000" in text
    assert "2790" in text
    assert "775" in text
    assert "2024" in text


def test_instruction_mentions_fields():
    tax_result = _make_tax_result()
    text = generate_instruction(tax_result, tax_year=2024)
    assert "Ф1" in text
    assert "cabinet.tax.gov.ua" in text


def test_f1_table_groups_by_ticker():
    positions = [
        {"ticker": "BAC.US", "isin": "US0605051046",
         "proceeds_uah": 20500.0, "cost_uah": 18900.0,
         "buy_commission_uah": 41.0, "sell_commission_uah": 45.1,
         "profit_uah": 1513.9},
        {"ticker": "BAC.US", "isin": "US0605051046",
         "proceeds_uah": 5000.0, "cost_uah": 4500.0,
         "buy_commission_uah": 10.0, "sell_commission_uah": 12.5,
         "profit_uah": 477.5},
        {"ticker": "JNJ.US", "isin": "US4781601046",
         "proceeds_uah": 8250.0, "cost_uah": 7800.0,
         "buy_commission_uah": 0.0, "sell_commission_uah": 0.0,
         "profit_uah": 450.0},
    ]
    text = generate_f1_table(positions, tax_year=2025)
    # BAC.US grouped: proceeds=25500, expenses=23508.6, profit=1991.4
    assert "BAC.US" in text
    assert "JNJ.US" in text
    assert "25500" in text  # grouped proceeds for BAC.US
    assert "2025" in text
    # Only 2 rows (not 3) — BAC.US merged
    assert text.count("BAC.US") == 1


def test_f1_table_loss_row():
    positions = [
        {"ticker": "XYZ.US", "isin": "US9999",
         "proceeds_uah": 8000.0, "cost_uah": 10000.0,
         "buy_commission_uah": 0.0, "sell_commission_uah": 0.0,
         "profit_uah": -2000.0},
    ]
    text = generate_f1_table(positions, tax_year=2025)
    assert "-2000" in text


def test_f1_table_empty():
    text = generate_f1_table([], tax_year=2025)
    assert "Ф1" in text
    assert "немає" in text.lower() or "відсутні" in text.lower() or "0" in text
