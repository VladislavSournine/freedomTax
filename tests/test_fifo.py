import pytest
from unittest.mock import MagicMock
from src.fifo import FIFOCalculator


def make_nbu(rate=41.0):
    nbu = MagicMock()
    nbu.get_rate.return_value = rate
    return nbu


def test_single_buy_no_closed_positions():
    nbu = make_nbu()
    calc = FIFOCalculator(nbu)
    trades = [
        {"trade_id": 1, "ticker": "AAPL.US", "isin": "US0378331005",
         "operation": "buy", "price": 100.0, "quantity": 10,
         "currency": "USD", "commission": 1.0, "settlement_date": "2024-11-15"},
    ]
    result = calc.calculate(trades, tax_year=2024)
    assert result == []


def test_buy_then_sell_full():
    nbu = make_nbu(41.0)
    calc = FIFOCalculator(nbu)
    trades = [
        {"trade_id": 1, "ticker": "AAPL.US", "isin": "US0378331005",
         "operation": "buy", "price": 100.0, "quantity": 10,
         "currency": "USD", "commission": 1.0, "settlement_date": "2024-11-15"},
        {"trade_id": 2, "ticker": "AAPL.US", "isin": "US0378331005",
         "operation": "sell", "price": 110.0, "quantity": 10,
         "currency": "USD", "commission": 1.1, "settlement_date": "2024-12-02"},
    ]
    result = calc.calculate(trades, tax_year=2024)
    assert len(result) == 1
    pos = result[0]
    assert pos["ticker"] == "AAPL.US"
    assert pos["quantity"] == 10
    # proceeds = 110 * 10 * 41 = 45100
    assert abs(pos["proceeds_uah"] - 45100.0) < 0.01
    # cost = 100 * 10 * 41 = 41000
    assert abs(pos["cost_uah"] - 41000.0) < 0.01
    # buy_commission = 1.0 * 41 = 41
    assert abs(pos["buy_commission_uah"] - 41.0) < 0.01
    # sell_commission = 1.1 * 41 = 45.1
    assert abs(pos["sell_commission_uah"] - 45.1) < 0.01
    # profit = 45100 - 41000 - 41 - 45.1 = 4013.9
    assert abs(pos["profit_uah"] - 4013.9) < 0.01


def test_partial_sell_fifo_order():
    nbu = make_nbu(40.0)
    calc = FIFOCalculator(nbu)
    trades = [
        {"trade_id": 1, "ticker": "BAC.US", "isin": "US123",
         "operation": "buy", "price": 50.0, "quantity": 10,
         "currency": "USD", "commission": 0.5, "settlement_date": "2024-11-15"},
        {"trade_id": 2, "ticker": "BAC.US", "isin": "US123",
         "operation": "buy", "price": 55.0, "quantity": 10,
         "currency": "USD", "commission": 0.55, "settlement_date": "2024-11-20"},
        {"trade_id": 3, "ticker": "BAC.US", "isin": "US123",
         "operation": "sell", "price": 60.0, "quantity": 12,
         "currency": "USD", "commission": 0.72, "settlement_date": "2024-12-05"},
    ]
    result = calc.calculate(trades, tax_year=2024)
    # First lot fully consumed (10), second lot partially (2)
    assert len(result) == 2
    quantities = [r["quantity"] for r in result]
    assert 10 in quantities
    assert 2 in quantities


def test_only_tax_year_sales_returned():
    nbu = make_nbu(41.0)
    calc = FIFOCalculator(nbu)
    trades = [
        {"trade_id": 1, "ticker": "MSFT.US", "isin": "US0",
         "operation": "buy", "price": 300.0, "quantity": 5,
         "currency": "USD", "commission": 1.5, "settlement_date": "2024-11-15"},
        {"trade_id": 2, "ticker": "MSFT.US", "isin": "US0",
         "operation": "sell", "price": 320.0, "quantity": 5,
         "currency": "USD", "commission": 1.6, "settlement_date": "2025-01-10"},
    ]
    result_2024 = calc.calculate(trades, tax_year=2024)
    result_2025 = calc.calculate(trades, tax_year=2025)
    assert result_2024 == []
    assert len(result_2025) == 1


def test_loss_position():
    nbu = make_nbu(41.0)
    calc = FIFOCalculator(nbu)
    trades = [
        {"trade_id": 1, "ticker": "XYZ.US", "isin": "US99",
         "operation": "buy", "price": 100.0, "quantity": 10,
         "currency": "USD", "commission": 1.0, "settlement_date": "2024-11-15"},
        {"trade_id": 2, "ticker": "XYZ.US", "isin": "US99",
         "operation": "sell", "price": 80.0, "quantity": 10,
         "currency": "USD", "commission": 0.8, "settlement_date": "2024-12-05"},
    ]
    result = calc.calculate(trades, tax_year=2024)
    assert result[0]["profit_uah"] < 0
