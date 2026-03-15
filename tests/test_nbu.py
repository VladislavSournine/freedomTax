import json
import pytest
from unittest.mock import patch, MagicMock
from src.nbu import get_rate, NBUClient


def make_api_response(date_str, currency, rate):
    return [{"exchangedate": date_str, "cc": currency, "rate": rate}]


def test_get_rate_returns_float(tmp_path):
    cache_file = tmp_path / "nbu_rates.json"
    client = NBUClient(cache_path=str(cache_file))

    with patch("src.nbu.requests.get") as mock_get:
        mock_get.return_value.json.return_value = make_api_response("14.11.2024", "USD", 41.2446)
        mock_get.return_value.raise_for_status = MagicMock()
        rate = client.get_rate("USD", "2024-11-14")

    assert isinstance(rate, float)
    assert abs(rate - 41.2446) < 0.001


def test_get_rate_cached(tmp_path):
    cache_file = tmp_path / "nbu_rates.json"
    client = NBUClient(cache_path=str(cache_file))

    with patch("src.nbu.requests.get") as mock_get:
        mock_get.return_value.json.return_value = make_api_response("14.11.2024", "USD", 41.2446)
        mock_get.return_value.raise_for_status = MagicMock()
        client.get_rate("USD", "2024-11-14")
        client.get_rate("USD", "2024-11-14")  # second call

    assert mock_get.call_count == 1  # API called only once


def test_get_rate_persists_cache(tmp_path):
    cache_file = tmp_path / "nbu_rates.json"

    with patch("src.nbu.requests.get") as mock_get:
        mock_get.return_value.json.return_value = make_api_response("14.11.2024", "USD", 41.2446)
        mock_get.return_value.raise_for_status = MagicMock()
        client1 = NBUClient(cache_path=str(cache_file))
        client1.get_rate("USD", "2024-11-14")

    with patch("src.nbu.requests.get") as mock_get2:
        client2 = NBUClient(cache_path=str(cache_file))
        rate = client2.get_rate("USD", "2024-11-14")

    assert mock_get2.call_count == 0  # loaded from file cache
    assert abs(rate - 41.2446) < 0.001


def test_get_rate_falls_back_to_previous_day(tmp_path):
    cache_file = tmp_path / "nbu_rates.json"
    client = NBUClient(cache_path=str(cache_file))

    # Weekend: 2024-11-16 (Saturday) — API returns empty, then try Friday 2024-11-15
    def api_side_effect(url, **kwargs):
        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        if "20241116" in url:
            mock.json.return_value = []
        else:
            mock.json.return_value = make_api_response("15.11.2024", "USD", 41.5)
        return mock

    with patch("src.nbu.requests.get", side_effect=api_side_effect):
        rate = client.get_rate("USD", "2024-11-16")

    assert abs(rate - 41.5) < 0.001


def test_get_rate_raises_after_5_empty_days(tmp_path):
    cache_file = tmp_path / "nbu_rates.json"
    client = NBUClient(cache_path=str(cache_file))

    with patch("src.nbu.requests.get") as mock_get:
        mock_get.return_value.json.return_value = []
        mock_get.return_value.raise_for_status = MagicMock()
        with pytest.raises(RuntimeError, match="USD"):
            client.get_rate("USD", "2024-11-14")
