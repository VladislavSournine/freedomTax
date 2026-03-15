import re
from typing import Any


def parse_freedom_json(data: dict[str, Any]) -> dict:
    cash_flows = data.get("cash_flows", {}).get("detailed", [])
    trades = _parse_trades(data.get("trades", {}).get("detailed", []))
    dividends = _parse_dividends(cash_flows)
    other_income = _parse_other_income(cash_flows)
    withholding_taxes = _parse_withholding_taxes(cash_flows)
    return {
        "trades": trades,
        "dividends": dividends,
        "other_income": other_income,
        "withholding_taxes": withholding_taxes,
    }


def _parse_trades(raw: list) -> list:
    result = []
    for t in raw:
        if t.get("operation") not in ("buy", "sell"):
            continue
        ticker = t["instr_nm"]
        # Skip forex pairs (e.g. EUR/USD) — currency conversions, not securities
        if "/" in ticker:
            continue
        result.append({
            "trade_id": t["trade_id"],
            "date": t["date"],
            "settlement_date": t["pay_d"],
            "ticker": ticker,
            "isin": t.get("isin", ""),
            "operation": t["operation"],
            "price": float(t["p"]),
            "quantity": float(t["q"]),
            "currency": t["curr_c"],
            "commission": float(t.get("commission") or 0),
        })
    return result


def _parse_dividends(raw: list) -> list:
    result = []
    for item in raw:
        if item.get("type_id") != "dividend":
            continue
        company, ticker = _parse_dividend_comment(item.get("comment", ""))
        result.append({
            "date": item["date"],
            "company": company,
            "ticker": ticker,
            "amount": float(item.get("amount") or 0),
            "currency": item.get("currency", "USD"),
        })
    return result


def _parse_other_income(raw: list) -> list:
    """Parse scores_rebate entries as 'інші доходи' (loyalty program cashback)."""
    result = []
    for item in raw:
        if item.get("type_id") != "scores_rebate":
            continue
        result.append({
            "date": item["date"],
            "amount": float(item.get("amount") or 0),
            "currency": item.get("currency", "USD"),
            "comment": item.get("comment", ""),
        })
    return result


def _parse_withholding_taxes(raw: list) -> list:
    """Parse 'tax' entries — US withholding tax deducted from dividends at source."""
    result = []
    for item in raw:
        if item.get("type_id") != "tax":
            continue
        result.append({
            "date": item["date"],
            "amount": abs(float(item.get("amount") or 0)),
            "currency": item.get("currency", "USD"),
        })
    return result


def _parse_dividend_comment(comment: str) -> tuple[str, str]:
    """Extract company name and ticker from Freedom24 dividend comment.

    Expected format: "Dividends on security (Company Name (TICKER.EXCHANGE)), ..."
    """
    match = re.search(r"Dividends on security \((.+?) \(([^)]+)\)\)", comment)
    if match:
        return match.group(1), match.group(2)
    return "Unknown", "Unknown"
