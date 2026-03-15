import json
import os
from datetime import date, timedelta
from typing import Optional

import requests


class NBUClient:
    BASE_URL = "https://bank.gov.ua/NBU_Exchange/exchange_site"

    def __init__(self, cache_path: str = "cache/nbu_rates.json"):
        self.cache_path = cache_path
        self._cache: dict = self._load_cache()

    def get_rate(self, currency: str, date_str: str) -> float:
        """Return UAH rate for currency on date_str (YYYY-MM-DD).

        Falls back to the most recent prior business day (up to 5 days back)
        if the API returns no data for the requested date.
        """
        key = f"{currency}:{date_str}"
        if key in self._cache:
            return self._cache[key]

        d = date.fromisoformat(date_str)
        for _ in range(5):
            rate = self._fetch(currency, d)
            if rate is not None:
                self._cache[key] = rate
                self._save_cache()
                return rate
            d -= timedelta(days=1)

        raise RuntimeError(
            f"Could not fetch NBU rate for {currency} on {date_str} "
            f"(tried 5 prior days). Check your internet connection."
        )

    def _fetch(self, currency: str, d: date) -> Optional[float]:
        date_str = d.strftime("%Y%m%d")
        url = f"{self.BASE_URL}?start={date_str}&end={date_str}&valcode={currency}&json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not data:
            return None
        return float(data[0]["rate"])

    def _load_cache(self) -> dict:
        if os.path.exists(self.cache_path):
            with open(self.cache_path) as f:
                return json.load(f)
        return {}

    def _save_cache(self) -> None:
        os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
        with open(self.cache_path, "w") as f:
            json.dump(self._cache, f, indent=2)


# Module-level convenience (uses default cache path)
_default_client: Optional[NBUClient] = None


def get_rate(currency: str, date_str: str) -> float:
    global _default_client
    if _default_client is None:
        _default_client = NBUClient()
    return _default_client.get_rate(currency, date_str)
