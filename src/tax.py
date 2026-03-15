from __future__ import annotations

from datetime import date
from typing import Optional

PDFO_RATE = 0.18
# Max foreign WHT credit = 50% of ПДФО rate (ПКУ ст.13.4 practical cap).
# For US dividends (15% WHT > 9% cap), effective ПДФО rate on dividends = 9%.
PDFO_DIVIDEND_EFFECTIVE_RATE = 0.09
VZ_RATE_OLD = 0.015   # before 2024-12-01
VZ_RATE_NEW = 0.05    # from 2024-12-01

VZ_RATE_CHANGE_DATE = date(2024, 12, 1)

# osa.tax uses a single VZ rate per tax year:
# 2024 and earlier → 1.5%, 2025 and later → 5%
VZ_FIRST_YEAR_NEW_RATE = 2025


def vz_rate_for_date(settlement_date: str) -> float:
    d = date.fromisoformat(settlement_date)
    return VZ_RATE_NEW if d >= VZ_RATE_CHANGE_DATE else VZ_RATE_OLD


def vz_rate_for_year(tax_year: int) -> float:
    return VZ_RATE_NEW if tax_year >= VZ_FIRST_YEAR_NEW_RATE else VZ_RATE_OLD


def calculate_taxes(
    positions: list,
    dividends: list,
    tax_year: int,
    other_income: Optional[list] = None,
    withholding_taxes: Optional[list] = None,
) -> dict:
    """Calculate ПДФО and ВЗ matching osa.tax methodology.

    osa.tax rules observed:
    - ПДФО 18% on dividend income only (scores_rebate excluded from ПДФО)
    - ВЗ uses a single year-level rate: 1.5% for tax_year ≤ 2024, 5% for 2025+
    - ВЗ applies to both dividend income and other income (scores_rebate)
    - No foreign WHT credit applied
    """
    if other_income is None:
        other_income = []

    year_vz_rate = vz_rate_for_year(tax_year)

    # Investment profit
    gross_profit = sum(p["profit_uah"] for p in positions)
    net_profit = max(0.0, gross_profit)  # losses don't carry forward

    pdfo_trades = round(net_profit * PDFO_RATE, 2)
    vz_trades = round(net_profit * year_vz_rate, 2)

    # Dividends: effective ПДФО = 9% (18% - max 9% foreign WHT credit per ПКУ ст.13.4)
    # For US stocks with 15% WHT (W-8BEN), the credit is capped at 9% of dividend income.
    dividend_income = sum(d["amount_uah"] for d in dividends)
    wht_credit_uah = min(
        sum(t["amount_uah"] for t in (withholding_taxes or [])),
        dividend_income * (PDFO_RATE - PDFO_DIVIDEND_EFFECTIVE_RATE),
    )
    pdfo_dividends = round(max(0.0, dividend_income * PDFO_RATE - wht_credit_uah), 2)
    vz_dividends = round(dividend_income * year_vz_rate, 2)

    # Other income (scores_rebate): included in ПДФО at 18% and ВЗ at year rate
    other_income_uah = sum(i["amount_uah"] for i in other_income)
    pdfo_other = round(other_income_uah * PDFO_RATE, 2)
    vz_other = round(other_income_uah * year_vz_rate, 2)

    return {
        "gross_profit_uah": round(gross_profit, 2),
        "net_profit_uah": round(net_profit, 2),
        "dividend_income_uah": round(dividend_income, 2),
        "other_income_uah": round(other_income_uah, 2),
        "wht_credit_uah": round(wht_credit_uah, 2),
        "pdfo_trades": pdfo_trades,
        "pdfo_dividends": pdfo_dividends,
        "pdfo_other": pdfo_other,
        "pdfo_total": round(pdfo_trades + pdfo_dividends + pdfo_other, 2),
        "vz_trades": vz_trades,
        "vz_dividends": vz_dividends,
        "vz_other": vz_other,
        "vz_total": round(vz_trades + vz_dividends + vz_other, 2),
    }
