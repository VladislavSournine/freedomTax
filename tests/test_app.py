import io
import json
from unittest.mock import MagicMock, patch

import pytest
from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.test_client() as c:
        yield c


def test_upload_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Freedom24" in body
    assert "JSON" in body
    assert "відкриття рахунку" in body


def test_upload_page_has_year_select(client):
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert "2025" in body
    assert 'name="tax_year"' in body


def _minimal_freedom_json(tax_year: int) -> dict:
    """Minimal valid Freedom24 JSON with one dividend in tax_year."""
    return {
        "trades": {"detailed": []},
        "cash_flows": {
            "detailed": [
                {
                    "type_id": "dividend",
                    "date": f"{tax_year}-06-15",
                    "amount": "100.00",
                    "currency": "USD",
                    "comment": (
                        f"Dividends on security (Apple Inc (AAPL.US)), "
                        f"accrual date {tax_year}-06-15"
                    ),
                }
            ]
        },
    }


@patch("app.NBUClient")
def test_calculate_renders_result(mock_nbu_cls, client):
    # NBU rate = 40.00 UAH/USD (pinned)
    # 100 USD * 40.00 = 4000.00 UAH dividend
    # No withholding tax in fixture → wht_credit_uah = 0 → full 18% applies
    # pdfo_dividends = 4000.00 * 0.18 = 720.00 UAH
    # vz_dividends (2025, 5%) = 4000.00 * 0.05 = 200.00 UAH
    # pdfo_total = 720.00, vz_total = 200.00, total = 920.00
    mock_nbu = MagicMock()
    mock_nbu.get_rate.return_value = 40.00
    mock_nbu_cls.return_value = mock_nbu

    data = json.dumps(_minimal_freedom_json(2025)).encode()
    resp = client.post(
        "/calculate",
        data={"file": (io.BytesIO(data), "report.json"), "tax_year": "2025"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "2025" in body
    assert "ПДФО" in body
    assert "До сплати" in body
    assert "720.00" in body   # pdfo_dividends (18%, no WHT credit)
    assert "200.00" in body   # vz_dividends (5%)
    assert "920.00" in body   # total to pay


def test_calculate_no_file_shows_flash(client):
    resp = client.post("/calculate", data={"tax_year": "2025"},
                       content_type="multipart/form-data")
    assert resp.status_code == 302
    # Follow redirect and check flash message rendered
    resp2 = client.get(resp.headers["Location"])
    assert "Оберіть файл" in resp2.data.decode("utf-8")


def test_calculate_invalid_json_shows_flash(client):
    resp = client.post(
        "/calculate",
        data={"file": (io.BytesIO(b"not json"), "bad.json"), "tax_year": "2025"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    resp2 = client.get(resp.headers["Location"])
    assert "Невірний формат" in resp2.data.decode("utf-8")


def _freedom_json_with_trades(tax_year: int) -> dict:
    """Freedom24 JSON with one buy and one sell trade for AAPL in tax_year."""
    return {
        "trades": {
            "detailed": [
                {
                    "trade_id": "1",
                    "date": f"{tax_year}-03-01",
                    "pay_d": f"{tax_year}-03-03",
                    "instr_nm": "AAPL",
                    "isin": "US0378331005",
                    "operation": "buy",
                    "p": "150.00",
                    "q": "10",
                    "curr_c": "USD",
                    "commission": "1.50",
                },
                {
                    "trade_id": "2",
                    "date": f"{tax_year}-06-01",
                    "pay_d": f"{tax_year}-06-03",
                    "instr_nm": "AAPL",
                    "isin": "US0378331005",
                    "operation": "sell",
                    "p": "170.00",
                    "q": "10",
                    "curr_c": "USD",
                    "commission": "1.70",
                },
            ]
        },
        "cash_flows": {"detailed": []},
    }


@patch("app.NBUClient")
def test_calculate_renders_f1_trades_table(mock_nbu_cls, client):
    """F1 table renders when there are closed positions (buy + sell same ticker)."""
    mock_nbu = MagicMock()
    mock_nbu.get_rate.return_value = 40.00
    mock_nbu_cls.return_value = mock_nbu

    data = json.dumps(_freedom_json_with_trades(2025)).encode()
    resp = client.post(
        "/calculate",
        data={"file": (io.BytesIO(data), "report.json"), "tax_year": "2025"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "AAPL" in body
    assert "УСЬОГО" in body


def test_calculate_invalid_year_shows_flash(client):
    data = json.dumps({"trades": {"detailed": []},
                       "cash_flows": {"detailed": []}}).encode()
    resp = client.post(
        "/calculate",
        data={"file": (io.BytesIO(data), "r.json"), "tax_year": "1999"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    resp2 = client.get(resp.headers["Location"])
    assert "Невірний звітний рік" in resp2.data.decode("utf-8")
