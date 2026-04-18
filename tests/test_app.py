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
    # Cabinet-export section must render with the letter totals wired up
    # (letter_total = 4000.00 here; no "other income" in the minimal fixture).
    assert 'name="letter_total" value="4000.00"' in body
    assert 'name="letter_pdfo" value="720.00"' in body
    assert 'name="letter_vz" value="200.00"' in body
    assert "export-cabinet-pdf" in body
    assert "ряд. 10.10" in body  # suggested Короткий зміст rendered


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
def test_calculate_manual_letter_vykh_overrides_parsed(mock_nbu_cls, client):
    """When Cyrillic in вих. № gets garbled by PDF Ctrl+C (e.g. Ж→712), the
    user's plain-text paste from «Вхідні документи» must win over whatever
    the parser extracted from the letter body."""
    mock_nbu = MagicMock()
    mock_nbu.get_rate.return_value = 40.00
    mock_nbu_cls.return_value = mock_nbu

    # Letter body with a parseable (but wrong/garbled) вих. number.
    letter_body = (
        "ДЕРЖАВНА ПОДАТКОВА СЛУЖБА УКРАЇНИ\n"
        "№1995671226-15-24-01-02-12 від 16.04.2026\n"
        "Про надання документів щодо декларації"
    )
    data = json.dumps(_minimal_freedom_json(2025)).encode()
    resp = client.post(
        "/calculate",
        data={
            "file": (io.BytesIO(data), "report.json"),
            "tax_year": "2025",
            "dps_letter_text": letter_body,
            "letter_vykh_manual": "19956/Ж12/26-15-24-01-02-12",
            "letter_date_manual": "16.04.2026",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    # Correct (manual) number must end up in both the letter and the
    # cabinet-export hidden fields.
    assert "19956/Ж12/26-15-24-01-02-12" in body
    # Garbled parsed version must not appear anywhere in the rendered output.
    assert "1995671226-15-24-01-02-12" not in body


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


_DRAFT_XML = (
    b'<?xml version="1.0" encoding="windows-1251"?>'
    b'<DECLAR xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    b'<DECLARHEAD><TIN>2745810755</TIN></DECLARHEAD>'
    b'<DECLARBODY>'
    b'<R010G3>0</R010G3><R010G4>0</R010G4><R010G5>0</R010G5>'
    b'<R010G6>0</R010G6><R010G7>0</R010G7>'
    b'<R0103G3>1000.00</R0103G3>'
    b'<R011G3>0</R011G3>'
    b'<HFILL>17042026</HFILL>'
    b'</DECLARBODY></DECLAR>'
)


def test_patch_xml_returns_attachment(client):
    resp = client.post(
        "/patch-xml",
        data={
            "xml": (io.BytesIO(_DRAFT_XML), "draft.xml"),
            "foreign_income": "15000.50",
            "pdfo_foreign": "1350.05",
            "vz_foreign": "750.03",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert "attachment" in resp.headers["Content-Disposition"]
    assert "F0100215_patched.xml" in resp.headers["Content-Disposition"]
    assert resp.mimetype == "application/xml"
    body = resp.data
    # Cyrillic country string round-trips through cp1251
    assert "США".encode("windows-1251") in body
    assert b"<R01010G3>15000.50</R01010G3>" in body
    # R010G3 = salary (1000.00) + foreign (15000.50) = 16000.50
    assert b"<R010G3>16000.50</R010G3>" in body


def test_patch_xml_no_file_redirects_with_flash(client):
    resp = client.post(
        "/patch-xml",
        data={"foreign_income": "100.00"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    resp2 = client.get(resp.headers["Location"])
    assert "чернетк" in resp2.data.decode("utf-8")


def test_patch_xml_malformed_xml_flashes_error(client):
    resp = client.post(
        "/patch-xml",
        data={"xml": (io.BytesIO(b"<not xml"), "bad.xml"),
              "foreign_income": "100.00"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    resp2 = client.get(resp.headers["Location"])
    assert "пошкоджений" in resp2.data.decode("utf-8")


def _cabinet_form_fields() -> dict:
    """Hidden-field payload that result.html re-submits to /export-cabinet-pdf.
    Mirrors the set of keys the route reads from request.form."""
    return {
        "tax_year": "2025",
        "pib_nominative": "Сурнін Владислав Олександрович",
        "rnokpp": "1234567890",
        "address": "м. Київ, вул. Приклад, 1",
        "contact_email": "test@example.com",
        "contact_phone": "+380991234567",
        "letter_vykh": "19956/Ж12/26-15-24-01-02-12",
        "letter_date": "16.04.2026",
        "declaration_num": "9999999999",
        "declaration_date": "01.04.2026",
        "freedom24_account": "F24-12345",
        "letter1_vykh": "123/Ж10/26-15-24",
        "letter1_date": "10.03.2026",
        "zvit_nova_num": "8888888888",
        "zvit_nova_date": "20.04.2026",
        "letter_total": "15000.50",
        "letter_pdfo": "1350.05",
        "letter_vz": "750.03",
    }


def _sample_pdf(marker: str) -> bytes:
    """A real PDF produced via our own pipeline — smallest way to get
    a parseable multi-page-capable PDF into the test without bundling a fixture."""
    from src.pdf_export import letter_to_pdf
    return letter_to_pdf(f"Sample content {marker}")


def test_export_cabinet_pdf_returns_merged_download(client):
    from pypdf import PdfReader
    fields = _cabinet_form_fields()
    data = {
        **fields,
        "freedom24_pdf": (io.BytesIO(_sample_pdf("FREEDOM")), "f24.pdf"),
    }
    resp = client.post(
        "/export-cabinet-pdf", data=data, content_type="multipart/form-data"
    )
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert "Vidpovid_DPS_2025.pdf" in resp.headers["Content-Disposition"]
    # Merged = cover letter (≥1 page) + Freedom24 PDF (1 page here) ⇒ ≥ 2.
    merged = PdfReader(io.BytesIO(resp.data))
    assert len(merged.pages) >= 2


def test_export_cabinet_pdf_includes_f1419104_when_uploaded(client):
    from pypdf import PdfReader
    fields = _cabinet_form_fields()
    data = {
        **fields,
        "freedom24_pdf": (io.BytesIO(_sample_pdf("FREEDOM")), "f24.pdf"),
        "f1419104_pdf": (io.BytesIO(_sample_pdf("DRFO")), "drfo.pdf"),
    }
    resp = client.post(
        "/export-cabinet-pdf", data=data, content_type="multipart/form-data"
    )
    assert resp.status_code == 200
    merged = PdfReader(io.BytesIO(resp.data))
    # Extra DRFO page pushes count one higher than the baseline two-blob case.
    assert len(merged.pages) >= 3
    # The letter text must reference F1419104 only in this branch.
    letter_text = merged.pages[0].extract_text() or ""
    assert "F1419104" in letter_text


def test_export_cabinet_pdf_without_f1419104_omits_drfo_bullet(client):
    from pypdf import PdfReader
    fields = _cabinet_form_fields()
    data = {
        **fields,
        "freedom24_pdf": (io.BytesIO(_sample_pdf("FREEDOM")), "f24.pdf"),
    }
    resp = client.post(
        "/export-cabinet-pdf", data=data, content_type="multipart/form-data"
    )
    assert resp.status_code == 200
    letter_text = PdfReader(io.BytesIO(resp.data)).pages[0].extract_text() or ""
    assert "F1419104" not in letter_text


def test_export_cabinet_pdf_missing_freedom24_flashes(client):
    fields = _cabinet_form_fields()
    resp = client.post(
        "/export-cabinet-pdf", data=fields, content_type="multipart/form-data"
    )
    assert resp.status_code == 302
    resp2 = client.get(resp.headers["Location"])
    assert "Freedom24" in resp2.data.decode("utf-8")


def test_export_cabinet_pdf_rejects_corrupt_freedom24(client):
    """A non-PDF blob masquerading as freedom24_pdf must flash, not 500.
    Apostrophes render HTML-escaped (Jinja autoescape → &#39;), so we match
    on a fragment of the flash that is unaffected by escaping."""
    fields = _cabinet_form_fields()
    data = {
        **fields,
        "freedom24_pdf": (io.BytesIO(b"not a pdf"), "f24.pdf"),
    }
    resp = client.post(
        "/export-cabinet-pdf", data=data, content_type="multipart/form-data"
    )
    assert resp.status_code == 302
    body = client.get(resp.headers["Location"]).data.decode("utf-8")
    assert "Не вдалося" in body
    assert 'class="flash"' in body
