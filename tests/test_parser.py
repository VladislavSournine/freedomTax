from src.parser import parse_freedom_json

SAMPLE = {
    "trades": {
        "detailed": [
            {
                "trade_id": 1,
                "date": "2024-11-13 16:30:02",
                "pay_d": "2024-11-14",
                "instr_nm": "BAC.US",
                "isin": "US0605051046",
                "operation": "buy",
                "p": 46.14,
                "q": 10,
                "curr_c": "USD",
                "commission": 1.44,
                "commission_currency": "USD",
            },
            {
                "trade_id": 2,
                "date": "2024-12-01 10:00:00",
                "pay_d": "2024-12-02",
                "instr_nm": "BAC.US",
                "isin": "US0605051046",
                "operation": "sell",
                "p": 50.00,
                "q": 5,
                "curr_c": "USD",
                "commission": 1.00,
                "commission_currency": "USD",
            },
        ]
    },
    "cash_flows": {
        "detailed": [
            {
                "date": "2024-12-11",
                "amount": 1.24,
                "currency": "USD",
                "type": "Dividends",
                "type_id": "dividend",
                "comment": "Dividends on security (Johnson & Johnson (JNJ.US)), record date 2024-11-26.",
            },
            {
                "date": "2024-12-11",
                "amount": 50.00,
                "currency": "USD",
                "type": "Deposit",
                "type_id": "deposit",
                "comment": "Deposit with a bank card",
            },
        ]
    },
}


def test_parse_trades_count():
    result = parse_freedom_json(SAMPLE)
    assert len(result["trades"]) == 2


def test_parse_trade_fields():
    result = parse_freedom_json(SAMPLE)
    trade = result["trades"][0]
    assert trade["trade_id"] == 1
    assert trade["date"] == "2024-11-13 16:30:02"
    assert trade["ticker"] == "BAC.US"
    assert trade["isin"] == "US0605051046"
    assert trade["operation"] == "buy"
    assert trade["price"] == 46.14
    assert trade["quantity"] == 10
    assert trade["currency"] == "USD"
    assert trade["commission"] == 1.44
    assert trade["settlement_date"] == "2024-11-14"


def test_parse_dividends_only():
    result = parse_freedom_json(SAMPLE)
    assert len(result["dividends"]) == 1


def test_parse_dividend_fields():
    result = parse_freedom_json(SAMPLE)
    div = result["dividends"][0]
    assert div["date"] == "2024-12-11"
    assert div["amount"] == 1.24
    assert div["currency"] == "USD"
    assert div["company"] == "Johnson & Johnson"
    assert div["ticker"] == "JNJ.US"


def test_parse_dividend_unknown_comment():
    sample = dict(SAMPLE)
    sample["cash_flows"] = {
        "detailed": [
            {
                "date": "2024-12-11",
                "amount": 2.00,
                "currency": "USD",
                "type_id": "dividend",
                "comment": "",
            }
        ]
    }
    result = parse_freedom_json(sample)
    assert result["dividends"][0]["company"] == "Unknown"
    assert result["dividends"][0]["ticker"] == "Unknown"


def test_parse_trades_filters_non_buy_sell():
    sample = {
        "trades": {"detailed": [
            {"trade_id": 1, "date": "2024-11-13", "pay_d": "2024-11-14",
             "instr_nm": "AAPL.US", "isin": "US0378331005",
             "operation": "split", "p": 100.0, "q": 10,
             "curr_c": "USD", "commission": 0.0},
        ]},
        "cash_flows": {"detailed": []},
    }
    result = parse_freedom_json(sample)
    assert result["trades"] == []
