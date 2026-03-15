from unittest.mock import MagicMock
from src.fifo import enrich_dividends_with_uah


def test_dividend_uah_conversion():
    nbu = MagicMock()
    nbu.get_rate.return_value = 41.5
    dividends = [
        {"date": "2024-12-11", "amount": 1.24, "currency": "USD",
         "company": "JNJ", "ticker": "JNJ.US"}
    ]
    result = enrich_dividends_with_uah(dividends, nbu)
    assert abs(result[0]["amount_uah"] - 1.24 * 41.5) < 0.01
