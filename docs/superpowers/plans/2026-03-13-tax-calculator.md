# Tax Calculator Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Jupyter Notebook that parses a Freedom24 broker JSON, calculates Ukrainian investment taxes (FIFO, ПДФО 18%, ВЗ), and patches the user's existing XML declaration from cabinet.tax.gov.ua.

**Architecture:** Six focused Python modules in `src/` handle parsing, NBU rates, FIFO, tax, XML patching, and report generation. The notebook orchestrates them in sequential cells with visible intermediate tables. Tests live in `tests/` and run with pytest.

**Tech Stack:** Python 3.11+, pandas (display tables), requests (NBU API), lxml (XML), jupyter, pytest

---

## Chunk 1: Setup, Parser, NBU

### Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `config.json`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`
- Create: `cache/.gitkeep`

- [ ] **Step 1: Create requirements.txt**

```
pandas>=2.0
requests>=2.31
lxml>=5.0
jupyter>=1.0
notebook>=7.0
pytest>=8.0
ipykernel>=6.0
```

- [ ] **Step 2: Install dependencies**

```bash
cd /Volumes/DevSSD/Development/python/tax
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Expected: all packages installed without errors.

- [ ] **Step 3: Create directory structure**

```bash
mkdir -p src tests cache
touch src/__init__.py tests/__init__.py cache/.gitkeep
```

- [ ] **Step 4: Create config.json**

```json
{
  "last_name": "",
  "first_name": "",
  "middle_name": "",
  "tax_id": "",
  "address": "",
  "phone": ""
}
```

Save to `config.json`.

- [ ] **Step 5: Commit**

```bash
git init
git add requirements.txt config.json src/ tests/ cache/
git commit -m "chore: project setup"
```

---

### Task 2: Parser — `src/parser.py`

Reads Freedom24 JSON, returns two normalized lists: `trades` and `dividends`.

**Files:**
- Create: `src/parser.py`
- Create: `tests/test_parser.py`

**Data structures returned:**

```python
# Trade (buy or sell)
{
    "trade_id": int,
    "date": str,          # "2024-11-13 16:30:02"
    "settlement_date": str,  # pay_d: "2024-11-14"
    "ticker": str,        # "BAC.US"
    "isin": str,          # "US0605051046"
    "operation": str,     # "buy" or "sell"
    "price": float,       # per share
    "quantity": float,
    "currency": str,      # "USD" or "EUR"
    "commission": float,  # always USD
}

# Dividend
{
    "date": str,          # accrual date "2024-12-11"
    "company": str,       # "Johnson & Johnson" (parsed from comment)
    "ticker": str,        # "JNJ.US" (parsed from comment)
    "amount": float,      # gross amount
    "currency": str,      # "USD"
}
```

- [ ] **Step 1: Write failing tests**

Create `tests/test_parser.py`:

```python
import json
import pytest
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_parser.py -v
```

Expected: `ImportError: cannot import name 'parse_freedom_json'`

- [ ] **Step 3: Implement `src/parser.py`**

```python
import re
from typing import Any


def parse_freedom_json(data: dict[str, Any]) -> dict:
    trades = _parse_trades(data.get("trades", {}).get("detailed", []))
    dividends = _parse_dividends(data.get("cash_flows", {}).get("detailed", []))
    return {"trades": trades, "dividends": dividends}


def _parse_trades(raw: list) -> list:
    result = []
    for t in raw:
        if t.get("operation") not in ("buy", "sell"):
            continue
        result.append({
            "trade_id": t["trade_id"],
            "date": t["date"],
            "settlement_date": t["pay_d"],
            "ticker": t["instr_nm"],
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


def _parse_dividend_comment(comment: str) -> tuple[str, str]:
    """Extract company name and ticker from Freedom24 dividend comment.

    Expected format: "Dividends on security (Company Name (TICKER.EXCHANGE)), ..."
    """
    match = re.search(r"Dividends on security \((.+?) \(([^)]+)\)\)", comment)
    if match:
        return match.group(1), match.group(2)
    return "Unknown", "Unknown"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_parser.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/parser.py tests/test_parser.py
git commit -m "feat: add Freedom24 JSON parser"
```

---

### Task 3: NBU Exchange Rates — `src/nbu.py`

Fetches NBU exchange rates with local file cache. Supports USD and EUR. Falls back to previous business day if rate missing.

**Files:**
- Create: `src/nbu.py`
- Create: `tests/test_nbu.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_nbu.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_nbu.py -v
```

Expected: `ImportError: cannot import name 'get_rate'`

- [ ] **Step 3: Implement `src/nbu.py`**

```python
import json
import os
from datetime import date, timedelta

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

    def _fetch(self, currency: str, d: date) -> float | None:
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
_default_client: NBUClient | None = None


def get_rate(currency: str, date_str: str) -> float:
    global _default_client
    if _default_client is None:
        _default_client = NBUClient()
    return _default_client.get_rate(currency, date_str)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_nbu.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nbu.py tests/test_nbu.py
git commit -m "feat: add NBU exchange rate client with caching"
```

---

## Chunk 2: FIFO, Tax, Report

### Task 4: FIFO Calculator — `src/fifo.py`

Processes full trade history, returns closed positions for a given tax year.

**Files:**
- Create: `src/fifo.py`
- Create: `tests/test_fifo.py`

**Returns per closed position:**
```python
{
    "ticker": str,
    "isin": str,
    "buy_date": str,
    "sell_date": str,
    "sell_settlement_date": str,
    "quantity": float,
    "proceeds_usd": float,
    "cost_usd": float,
    "proceeds_uah": float,
    "cost_uah": float,
    "sell_commission_uah": float,
    "buy_commission_uah": float,
    "profit_uah": float,
}
```

- [ ] **Step 1: Write failing tests**

Create `tests/test_fifo.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_fifo.py -v
```

Expected: `ImportError: cannot import name 'FIFOCalculator'`

- [ ] **Step 3: Implement `src/fifo.py`**

```python
from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class BuyLot:
    ticker: str
    isin: str
    settlement_date: str
    quantity: float
    price: float
    currency: str
    nbu_rate: float
    commission_usd: float
    commission_nbu_rate: float
    remaining: float = field(init=False)

    def __post_init__(self):
        self.remaining = self.quantity


class FIFOCalculator:
    def __init__(self, nbu_client):
        self._nbu = nbu_client

    def calculate(self, trades: list, tax_year: int) -> list:
        """Process all trades, return closed positions for tax_year."""
        # Sort by settlement date to ensure correct FIFO order
        sorted_trades = sorted(trades, key=lambda t: t["settlement_date"])

        queues: dict[str, deque[BuyLot]] = defaultdict(deque)
        closed_positions = []

        for trade in sorted_trades:
            ticker = trade["ticker"]
            if trade["operation"] == "buy":
                nbu_rate = self._nbu.get_rate(trade["currency"], trade["settlement_date"])
                lot = BuyLot(
                    ticker=ticker,
                    isin=trade["isin"],
                    settlement_date=trade["settlement_date"],
                    quantity=trade["quantity"],
                    price=trade["price"],
                    currency=trade["currency"],
                    nbu_rate=nbu_rate,
                    commission_usd=trade["commission"],
                    commission_nbu_rate=self._nbu.get_rate("USD", trade["settlement_date"]),
                )
                queues[ticker].append(lot)

            elif trade["operation"] == "sell":
                sell_year = int(trade["settlement_date"][:4])
                sell_nbu = self._nbu.get_rate(trade["currency"], trade["settlement_date"])
                sell_commission_nbu = self._nbu.get_rate("USD", trade["settlement_date"])

                remaining_sell = trade["quantity"]
                queue = queues[ticker]

                if not queue:
                    raise RuntimeError(
                        f"FIFO queue empty for {ticker} on sell {trade['settlement_date']}. "
                        "No prior buy found — check that the report covers the full account history."
                    )

                while remaining_sell > 0:
                    if not queue:
                        raise RuntimeError(f"FIFO queue exhausted for {ticker}")
                    lot = queue[0]
                    filled = min(remaining_sell, lot.remaining)

                    proceeds_uah = trade["price"] * filled * sell_nbu
                    cost_uah = lot.price * filled * lot.nbu_rate

                    # Buy commission: proportional to filled qty from this lot
                    buy_comm_uah = (lot.commission_usd * filled / lot.quantity) * lot.commission_nbu_rate

                    # Sell commission: proportional to filled qty from this sell
                    sell_comm_uah = (trade["commission"] * filled / trade["quantity"]) * sell_commission_nbu

                    profit_uah = proceeds_uah - cost_uah - buy_comm_uah - sell_comm_uah

                    if sell_year == tax_year:
                        closed_positions.append({
                            "ticker": ticker,
                            "isin": trade["isin"],
                            "buy_date": lot.settlement_date,
                            "sell_date": trade["settlement_date"],
                            "sell_settlement_date": trade["settlement_date"],
                            "quantity": filled,
                            "proceeds_usd": trade["price"] * filled,
                            "cost_usd": lot.price * filled,
                            "proceeds_uah": round(proceeds_uah, 2),
                            "cost_uah": round(cost_uah, 2),
                            "buy_commission_uah": round(buy_comm_uah, 2),
                            "sell_commission_uah": round(sell_comm_uah, 2),
                            "profit_uah": round(profit_uah, 2),
                        })

                    lot.remaining -= filled
                    remaining_sell -= filled
                    if lot.remaining <= 1e-9:
                        queue.popleft()

        return closed_positions
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_fifo.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fifo.py tests/test_fifo.py
git commit -m "feat: add FIFO calculator"
```

---

### Task 5: Tax Calculator — `src/tax.py`

Applies ПДФО and ВЗ rates to positions and dividends.

**Files:**
- Create: `src/tax.py`
- Create: `tests/test_tax.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_tax.py`:

```python
import pytest
from src.tax import calculate_taxes, VZ_RATE_CHANGE_DATE


def test_vz_rate_before_cutoff():
    # Trades settled before 2024-12-01 → ВЗ 1.5%
    positions = [
        {"profit_uah": 10000.0, "sell_settlement_date": "2024-11-30",
         "proceeds_uah": 50000, "cost_uah": 40000,
         "buy_commission_uah": 0, "sell_commission_uah": 0}
    ]
    result = calculate_taxes(positions, dividends=[], tax_year=2024)
    assert abs(result["vz_total"] - 150.0) < 0.01  # 10000 * 1.5%


def test_vz_rate_after_cutoff():
    # Trades settled on/after 2024-12-01 → ВЗ 5%
    positions = [
        {"profit_uah": 10000.0, "sell_settlement_date": "2024-12-01",
         "proceeds_uah": 50000, "cost_uah": 40000,
         "buy_commission_uah": 0, "sell_commission_uah": 0}
    ]
    result = calculate_taxes(positions, dividends=[], tax_year=2024)
    assert abs(result["vz_total"] - 500.0) < 0.01  # 10000 * 5%


def test_pdfo_rate():
    positions = [
        {"profit_uah": 10000.0, "sell_settlement_date": "2024-12-01",
         "proceeds_uah": 50000, "cost_uah": 40000,
         "buy_commission_uah": 0, "sell_commission_uah": 0}
    ]
    result = calculate_taxes(positions, dividends=[], tax_year=2024)
    assert abs(result["pdfo_total"] - 1800.0) < 0.01  # 10000 * 18%


def test_loss_offsets_gain():
    positions = [
        {"profit_uah": 10000.0, "sell_settlement_date": "2024-12-05",
         "proceeds_uah": 50000, "cost_uah": 40000,
         "buy_commission_uah": 0, "sell_commission_uah": 0},
        {"profit_uah": -4000.0, "sell_settlement_date": "2024-12-10",
         "proceeds_uah": 20000, "cost_uah": 24000,
         "buy_commission_uah": 0, "sell_commission_uah": 0},
    ]
    result = calculate_taxes(positions, dividends=[], tax_year=2024)
    # Net = 6000, ПДФО = 1080, ВЗ = 300 (5% on net 6000)
    assert abs(result["net_profit_uah"] - 6000.0) < 0.01
    assert abs(result["pdfo_total"] - 1080.0) < 0.01
    assert abs(result["vz_trades"] - 300.0) < 0.01  # 6000 * 5% (net basis)


def test_vz_uses_net_not_gross():
    """ВЗ must be calculated on net profit, not gross gains."""
    positions = [
        {"profit_uah": 10000.0, "sell_settlement_date": "2024-12-05",
         "proceeds_uah": 50000, "cost_uah": 40000,
         "buy_commission_uah": 0, "sell_commission_uah": 0},
        {"profit_uah": -7000.0, "sell_settlement_date": "2024-11-20",
         "proceeds_uah": 20000, "cost_uah": 27000,
         "buy_commission_uah": 0, "sell_commission_uah": 0},
    ]
    result = calculate_taxes(positions, dividends=[], tax_year=2024)
    # Net = 3000; all net profit settled after 2024-12-01 → 5%
    # But the loss was settled before cutoff; we tax the NET 3000 at the
    # date of the profitable trade (2024-12-05) → 5% → ВЗ = 150
    assert abs(result["net_profit_uah"] - 3000.0) < 0.01
    assert abs(result["vz_trades"] - 150.0) < 0.01


def test_net_loss_zero_tax():
    positions = [
        {"profit_uah": -5000.0, "sell_settlement_date": "2024-12-05",
         "proceeds_uah": 10000, "cost_uah": 15000,
         "buy_commission_uah": 0, "sell_commission_uah": 0},
    ]
    result = calculate_taxes(positions, dividends=[], tax_year=2024)
    assert result["gross_profit_uah"] == -5000.0  # real figure preserved
    assert result["net_profit_uah"] == 0.0        # clamped tax base
    assert result["pdfo_total"] == 0.0
    assert result["vz_total"] == 0.0


def test_dividends_taxed_separately():
    dividends = [
        {"date": "2024-12-11", "amount_uah": 500.0, "company": "JNJ", "ticker": "JNJ.US"}
    ]
    result = calculate_taxes(positions=[], dividends=dividends, tax_year=2024)
    assert abs(result["dividend_income_uah"] - 500.0) < 0.01
    assert abs(result["pdfo_dividends"] - 90.0) < 0.01   # 500 * 18%
    assert abs(result["vz_dividends"] - 25.0) < 0.01     # 500 * 5%
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_tax.py -v
```

Expected: `ImportError: cannot import name 'calculate_taxes'`

- [ ] **Step 3: Implement `src/tax.py`**

```python
from datetime import date

PDFO_RATE = 0.18
VZ_RATE_OLD = 0.015   # before 2024-12-01
VZ_RATE_NEW = 0.05    # from 2024-12-01

VZ_RATE_CHANGE_DATE = date(2024, 12, 1)


def vz_rate_for_date(settlement_date: str) -> float:
    d = date.fromisoformat(settlement_date)
    return VZ_RATE_NEW if d >= VZ_RATE_CHANGE_DATE else VZ_RATE_OLD


def calculate_taxes(positions: list, dividends: list, tax_year: int) -> dict:
    """Calculate ПДФО and ВЗ for given positions and dividends.

    Positions must include 'sell_settlement_date' and 'profit_uah'.
    Dividends must include 'amount_uah' and 'date'.
    """
    # Investment profit
    gross_profit = sum(p["profit_uah"] for p in positions)
    net_profit = max(0.0, gross_profit)  # losses don't carry forward

    pdfo_trades = round(net_profit * PDFO_RATE, 2)

    # ВЗ: apply to net profit only (losses offset gains first per ПКУ 170.2).
    # Rate is determined by the settlement date of the profitable trade(s).
    # When net_profit < gross (i.e. some losses exist), we attribute the net
    # profit to the most recent profitable positions (conservative approach).
    vz_trades = 0.0
    if net_profit > 0:
        # Sort profitable positions by settlement date descending (most recent first)
        profitable = sorted(
            [p for p in positions if p["profit_uah"] > 0],
            key=lambda p: p["sell_settlement_date"],
            reverse=True,
        )
        remaining = net_profit
        for pos in profitable:
            if remaining <= 0:
                break
            taxable = min(pos["profit_uah"], remaining)
            rate = vz_rate_for_date(pos["sell_settlement_date"])
            vz_trades += taxable * rate
            remaining -= taxable
        vz_trades = round(vz_trades, 2)

    # Dividends (always use current rate — dividends are accrued, not traded)
    dividend_income = sum(d["amount_uah"] for d in dividends)
    dividend_vz_rate = VZ_RATE_NEW  # dividends accrued in 2024 use current rate (conservative)
    pdfo_dividends = round(dividend_income * PDFO_RATE, 2)
    vz_dividends = round(dividend_income * dividend_vz_rate, 2)

    return {
        "gross_profit_uah": round(gross_profit, 2),
        "net_profit_uah": round(net_profit, 2),
        "pdfo_total": round(pdfo_trades + pdfo_dividends, 2),
        "pdfo_trades": pdfo_trades,
        "pdfo_dividends": pdfo_dividends,
        "vz_total": round(vz_trades + vz_dividends, 2),
        "vz_trades": vz_trades,
        "vz_dividends": vz_dividends,
        "dividend_income_uah": round(dividend_income, 2),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_tax.py -v
```

Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tax.py tests/test_tax.py
git commit -m "feat: add tax calculator (ПДФО + ВЗ)"
```

---

### Task 6: Report Generator — `src/report.py`

Generates `instruction.txt` — plain-text fallback with numbers and field names.

**Files:**
- Create: `src/report.py`
- Create: `tests/test_report.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_report.py`:

```python
from src.report import generate_instruction


def test_instruction_contains_key_amounts():
    tax_result = {
        "net_profit_uah": 15000.0,
        "dividend_income_uah": 500.0,
        "pdfo_total": 2790.0,
        "pdfo_trades": 2700.0,
        "pdfo_dividends": 90.0,
        "vz_total": 775.0,
        "vz_trades": 750.0,
        "vz_dividends": 25.0,
        "gross_profit_uah": 15000.0,
    }
    text = generate_instruction(tax_result, tax_year=2024)
    assert "15000" in text
    assert "2790" in text
    assert "775" in text
    assert "2024" in text


def test_instruction_mentions_fields():
    tax_result = {
        "net_profit_uah": 0.0,
        "dividend_income_uah": 0.0,
        "pdfo_total": 0.0,
        "pdfo_trades": 0.0,
        "pdfo_dividends": 0.0,
        "vz_total": 0.0,
        "vz_trades": 0.0,
        "vz_dividends": 0.0,
        "gross_profit_uah": 0.0,
    }
    text = generate_instruction(tax_result, tax_year=2024)
    assert "Ф1" in text
    assert "cabinet.tax.gov.ua" in text
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_report.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `src/report.py`**

```python
def generate_instruction(tax_result: dict, tax_year: int) -> str:
    lines = [
        f"=== ІНСТРУКЦІЯ ДО ДЕКЛАРАЦІЇ ЗА {tax_year} РІК ===",
        "",
        "Ці цифри необхідно внести до декларації на cabinet.tax.gov.ua",
        "або вони вже внесені у файл declaration_patched.xml (додаток Ф1).",
        "",
        "--- ІНВЕСТИЦІЙНИЙ ПРИБУТОК (додаток Ф1) ---",
        f"Загальний прибуток від торгівлі:  {tax_result['net_profit_uah']:>12.2f} грн",
        f"  (до заліку збитків):             {tax_result['gross_profit_uah']:>12.2f} грн",
        "",
        "--- ДИВІДЕНДИ ---",
        f"Дохід від дивідендів:             {tax_result['dividend_income_uah']:>12.2f} грн",
        "",
        "--- ПОДАТКИ ---",
        f"ПДФО (18%) — торгівля:            {tax_result['pdfo_trades']:>12.2f} грн",
        f"ПДФО (18%) — дивіденди:           {tax_result['pdfo_dividends']:>12.2f} грн",
        f"ПДФО разом:                       {tax_result['pdfo_total']:>12.2f} грн",
        "",
        f"ВЗ — торгівля:                    {tax_result['vz_trades']:>12.2f} грн",
        f"ВЗ — дивіденди:                   {tax_result['vz_dividends']:>12.2f} грн",
        f"ВЗ разом:                         {tax_result['vz_total']:>12.2f} грн",
        "",
        "--- ЩО ВНОСИТИ ВРУЧНУ (якщо XML-патч не підійшов) ---",
        "1. Відкрийте cabinet.tax.gov.ua → Декларація про майновий стан і доходи",
        "2. Додайте додаток Ф1 (інвестиційний прибуток)",
        "   - Рядок 10.1: сума доходів від продажу ЦП (proceeds_uah разом)",
        "   - Рядок 10.2: витрати на придбання ЦП (cost_uah + комісії разом)",
        "   - Рядок 10.3: фінансовий результат (net_profit_uah)",
        "3. Дивіденди — Розділ II Ф1 або окремий рядок декларації",
        "   - Сума дивідендів: dividend_income_uah",
        "4. Розділ VI декларації — самостійно нараховані зобов'язання:",
        "   - ПДФО рядок: pdfo_total",
        "   - ВЗ рядок:   vz_total",
        "",
        "Примітка: збитки поточного року зараховуються (ПКУ ст.170.2),",
        "          але НЕ переносяться на наступний рік.",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_report.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/report.py tests/test_report.py
git commit -m "feat: add text instruction report generator"
```

---

## Chunk 3: XML Patcher, NBU Dividends, Notebook

### Task 7: Research ДПС XML Schema

Before implementing `xml_patcher.py`, the exact XSD schema for додаток Ф1 must be obtained.

**Files:**
- Create: `docs/f1_schema_notes.md` (findings from research)

- [ ] **Step 1: Download the XSD schema for form F0111306**

Open browser and navigate to:
`https://tax.gov.ua` → "Електронна звітність" → "Реєстр форм"

Search for "F0111306" (Додаток Ф1 до декларації про майновий стан і доходи).

Download the XSD file. Save it to `docs/F0111306.xsd`.

- [ ] **Step 2: Also download a sample filled XML**

In cabinet.tax.gov.ua, open a test declaration and export the XML. This is your reference for the actual structure used by the portal.

- [ ] **Step 3: Document the key XML elements**

Create `docs/f1_schema_notes.md` with:
- Root element name and namespace
- Element path for each row of investment income
- Element names for: ticker, ISIN, buy_date, sell_date, proceeds, cost, profit
- Element names for dividends section
- Totals elements (ПДФО, ВЗ)
- Taxpayer identity block element names

- [ ] **Step 4: Commit**

```bash
git add docs/
git commit -m "docs: add F1 XSD schema and field mapping notes"
```

---

### Task 8: Dividend UAH Conversion

Before the notebook works end-to-end, dividends need UAH amounts. This is done in the notebook orchestration layer, but tested here.

**Files:**
- Modify: `src/parser.py` — add `amount_uah` conversion helper (or do in notebook; keep parser pure)
- Create: `tests/test_dividend_uah.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_dividend_uah.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_dividend_uah.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Add `enrich_dividends_with_uah` to `src/fifo.py`**

Append to `src/fifo.py`:

```python
def enrich_dividends_with_uah(dividends: list, nbu_client) -> list:
    """Add amount_uah field to each dividend using NBU rate on accrual date."""
    result = []
    for div in dividends:
        rate = nbu_client.get_rate(div["currency"], div["date"])
        result.append({**div, "amount_uah": round(div["amount"] * rate, 2)})
    return result
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_dividend_uah.py tests/test_fifo.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fifo.py tests/test_dividend_uah.py
git commit -m "feat: add dividend UAH conversion"
```

---

### Task 9: XML Patcher — `src/xml_patcher.py`

**Note:** This task depends on the XSD schema research in Task 7. The element names below are placeholders — replace them with actual names from `docs/f1_schema_notes.md`.

**Files:**
- Create: `src/xml_patcher.py`
- Create: `tests/test_xml_patcher.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_xml_patcher.py`:

```python
import pytest
from lxml import etree
from src.xml_patcher import patch_declaration


SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<DECLAR>
  <DECLARHEAD>
    <TIN>1234567890</TIN>
  </DECLARHEAD>
  <DECLARBODY>
  </DECLARBODY>
</DECLAR>"""


def make_tax_result():
    return {
        "net_profit_uah": 15000.0,
        "dividend_income_uah": 500.0,
        "pdfo_total": 2790.0,
        "pdfo_trades": 2700.0,
        "pdfo_dividends": 90.0,
        "vz_total": 775.0,
        "vz_trades": 750.0,
        "vz_dividends": 25.0,
        "gross_profit_uah": 15000.0,
    }


def make_positions():
    return [
        {
            "ticker": "BAC.US", "isin": "US0605051046",
            "buy_date": "2024-11-15", "sell_date": "2024-12-02",
            "quantity": 10, "proceeds_uah": 20500.0, "cost_uah": 18900.0,
            "buy_commission_uah": 41.0, "sell_commission_uah": 45.1,
            "profit_uah": 1513.9,
        }
    ]


def make_dividends():
    return [
        {"company": "Johnson & Johnson", "ticker": "JNJ.US",
         "date": "2024-12-11", "amount_uah": 51.46}
    ]


def test_patch_validates_against_xsd_if_schema_exists(tmp_path, monkeypatch):
    """If XSD file is present, invalid XML raises ValueError."""
    import src.xml_patcher as patcher
    # Point to a minimal XSD that rejects our output
    minimal_xsd = tmp_path / "test.xsd"
    minimal_xsd.write_bytes(b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="STRICT_ROOT"/>
</xs:schema>""")
    monkeypatch.setattr(patcher, "XSD_SCHEMA_PATH", str(minimal_xsd))
    config = {"last_name": "T", "first_name": "T", "middle_name": "",
               "tax_id": "0", "address": "", "phone": ""}
    with pytest.raises(ValueError, match="XSD validation"):
        patch_declaration(SAMPLE_XML, [], [], {
            "pdfo_total": 0, "vz_total": 0
        }, config, 2024)


def test_patch_returns_valid_xml():
    config = {"last_name": "Шевченко", "first_name": "Тарас",
               "middle_name": "Григорович", "tax_id": "1234567890",
               "address": "Київ", "phone": ""}
    result_xml = patch_declaration(
        xml_bytes=SAMPLE_XML,
        positions=make_positions(),
        dividends=make_dividends(),
        tax_result=make_tax_result(),
        config=config,
        tax_year=2024,
    )
    # Must parse without error
    tree = etree.fromstring(result_xml)
    assert tree is not None


def test_patch_idempotent():
    """Calling patch twice produces the same result (no duplicate Ф1 nodes)."""
    from src.xml_patcher import TAG_F1_ROOT  # use the constant, not a hardcoded string
    config = {"last_name": "Test", "first_name": "Test",
               "middle_name": "", "tax_id": "0000000000",
               "address": "", "phone": ""}
    first = patch_declaration(
        SAMPLE_XML, make_positions(), make_dividends(), make_tax_result(), config, 2024
    )
    second = patch_declaration(
        first, make_positions(), make_dividends(), make_tax_result(), config, 2024
    )
    tree = etree.fromstring(second)
    f1_nodes = tree.findall(".//" + TAG_F1_ROOT)
    assert len(f1_nodes) == 1  # exactly one, never zero, never two
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_xml_patcher.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `src/xml_patcher.py`**

**Important:** Replace element names (e.g., `F0111306`, `HNUM`, `HKIND`) with the actual names from `docs/f1_schema_notes.md` after completing Task 7. Also set `XSD_SCHEMA_PATH` to the actual path of the downloaded XSD file.

```python
"""XML patcher for Ukrainian tax declaration (cabinet.tax.gov.ua).

Element names are based on the F0111306 XSD schema from tax.gov.ua.
Update TAG_* constants after confirming against the actual schema.
"""
import os
from lxml import etree

# Path to F0111306 XSD schema downloaded in Task 7
XSD_SCHEMA_PATH = "docs/F0111306.xsd"

# ── Update these constants after Task 7 (schema research) ──────────────
TAG_F1_ROOT = "F0111306"       # Ф1 appendix root element
TAG_TRADE_ROW = "HKIND"        # One row of investment income
TAG_DIV_ROW = "HDIV"           # One row of dividends
TAG_TICKER = "HNAME"
TAG_ISIN = "HISIN"
TAG_BUY_DATE = "HDATEB"
TAG_SELL_DATE = "HDATES"
TAG_PROCEEDS = "HSUMD"
TAG_COST = "HSUMC"
TAG_PROFIT = "HRESULT"
TAG_PDFO = "HPDFO"
TAG_VZ = "HVZ"
TAG_DIV_COMPANY = "HDIVNAME"
TAG_DIV_DATE = "HDIVDATE"
TAG_DIV_AMOUNT = "HDIVSUM"
# ────────────────────────────────────────────────────────────────────────


def patch_declaration(
    xml_bytes: bytes,
    positions: list,
    dividends: list,
    tax_result: dict,
    config: dict,
    tax_year: int,
) -> bytes:
    """Inject or replace Ф1 appendix in an existing declaration XML.

    Returns modified XML as bytes.
    """
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.fromstring(xml_bytes, parser)

    # Remove existing F1 appendix if present (idempotent)
    for existing in tree.findall(".//" + TAG_F1_ROOT):
        existing.getparent().remove(existing)

    f1 = etree.SubElement(tree, TAG_F1_ROOT)

    # Trade rows
    for pos in positions:
        row = etree.SubElement(f1, TAG_TRADE_ROW)
        etree.SubElement(row, TAG_TICKER).text = pos["ticker"]
        etree.SubElement(row, TAG_ISIN).text = pos["isin"]
        etree.SubElement(row, TAG_BUY_DATE).text = pos["buy_date"]
        etree.SubElement(row, TAG_SELL_DATE).text = pos["sell_date"]
        etree.SubElement(row, TAG_PROCEEDS).text = f"{pos['proceeds_uah']:.2f}"
        etree.SubElement(row, TAG_COST).text = f"{pos['cost_uah'] + pos['buy_commission_uah']:.2f}"
        etree.SubElement(row, TAG_PROFIT).text = f"{pos['profit_uah']:.2f}"

    # Dividend rows
    for div in dividends:
        row = etree.SubElement(f1, TAG_DIV_ROW)
        etree.SubElement(row, TAG_DIV_COMPANY).text = div["company"]
        etree.SubElement(row, TAG_DIV_DATE).text = div["date"]
        etree.SubElement(row, TAG_DIV_AMOUNT).text = f"{div['amount_uah']:.2f}"

    # Totals
    etree.SubElement(f1, TAG_PDFO).text = f"{tax_result['pdfo_total']:.2f}"
    etree.SubElement(f1, TAG_VZ).text = f"{tax_result['vz_total']:.2f}"

    result = etree.tostring(tree, encoding="UTF-8", xml_declaration=True, pretty_print=True)

    # Validate against XSD schema if available
    if os.path.exists(XSD_SCHEMA_PATH):
        with open(XSD_SCHEMA_PATH, "rb") as f:
            schema_doc = etree.parse(f)
        schema = etree.XMLSchema(schema_doc)
        result_tree = etree.fromstring(result)
        if not schema.validate(result_tree):
            errors = "\n".join(str(e) for e in schema.error_log)
            raise ValueError(f"Generated XML failed XSD validation:\n{errors}")

    return result
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_xml_patcher.py -v
```

Expected: both tests PASS. (idempotency test passes structurally — real element names adjusted after schema research)

- [ ] **Step 5: Commit**

```bash
git add src/xml_patcher.py tests/test_xml_patcher.py
git commit -m "feat: add XML declaration patcher for Ф1 appendix"
```

---

### Task 10: Assemble Jupyter Notebook — `tax_calculator.ipynb`

**Files:**
- Create: `tax_calculator.ipynb`

- [ ] **Step 1: Run all tests to confirm clean baseline**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 2: Create the notebook**

Create `tax_calculator.ipynb` with the following cells (use `jupyter notebook` or create programmatically):

**Cell 1 — Config (edit this cell each time):**
```python
import json, sys
sys.path.insert(0, ".")

FREEDOM_JSON_PATH = "~/Downloads/1709216_2024-11-12 23_59_59_2025-12-31 23_59_59_all.json"
DECLARATION_XML_PATH = "declaration.xml"   # downloaded from cabinet.tax.gov.ua
TAX_YEAR = 2025
OUTPUT_XML_PATH = "declaration_patched.xml"
OUTPUT_TXT_PATH = "instruction.txt"

with open("config.json") as f:
    config = json.load(f)

print(f"Tax year: {TAX_YEAR}")
print(f"Config: {config['last_name']} {config['first_name']}, ІПН: {config['tax_id']}")
```

**Cell 2 — Parse Freedom24 JSON:**
```python
import json
from pathlib import Path
from src.parser import parse_freedom_json

with open(Path(FREEDOM_JSON_PATH).expanduser()) as f:
    raw = json.load(f)

data = parse_freedom_json(raw)
print(f"Trades loaded:    {len(data['trades'])}")
print(f"Dividends loaded: {len(data['dividends'])}")
dates = [t['settlement_date'] for t in data['trades']]
print(f"Date range:       {min(dates)} — {max(dates)}")
```

**Cell 3 — Fetch NBU rates and calculate FIFO:**
```python
import pandas as pd
from src.nbu import NBUClient
from src.fifo import FIFOCalculator, enrich_dividends_with_uah

nbu = NBUClient()
calc = FIFOCalculator(nbu)

positions = calc.calculate(data["trades"], tax_year=TAX_YEAR)
dividends = enrich_dividends_with_uah(data["dividends"], nbu)

# Filter dividends for tax year
dividends_year = [d for d in dividends if d["date"].startswith(str(TAX_YEAR))]

print(f"Closed positions in {TAX_YEAR}: {len(positions)}")
if positions:
    df = pd.DataFrame(positions)[["ticker", "buy_date", "sell_date", "quantity",
                                   "proceeds_uah", "cost_uah", "profit_uah"]]
    display(df)
```

**Cell 4 — Dividends table:**
```python
if dividends_year:
    df_div = pd.DataFrame(dividends_year)[["date", "ticker", "company", "amount", "currency", "amount_uah"]]
    display(df_div)
else:
    print("No dividends in", TAX_YEAR)
```

**Cell 5 — Tax summary:**
```python
from src.tax import calculate_taxes

tax_result = calculate_taxes(positions, dividends_year, tax_year=TAX_YEAR)

print(f"\n{'='*45}")
print(f"  ПІДСУМОК ЗА {TAX_YEAR} РІК")
print(f"{'='*45}")
print(f"  Інвестиційний прибуток:  {tax_result['net_profit_uah']:>10.2f} грн")
print(f"  Дохід від дивідендів:   {tax_result['dividend_income_uah']:>10.2f} грн")
print(f"  ПДФО (18%):             {tax_result['pdfo_total']:>10.2f} грн")
print(f"  ВЗ:                     {tax_result['vz_total']:>10.2f} грн")
print(f"{'='*45}")
```

**Cell 6 — Patch XML:**
```python
from pathlib import Path
from src.xml_patcher import patch_declaration

xml_path = Path(DECLARATION_XML_PATH)
if xml_path.exists():
    with open(xml_path, "rb") as f:
        xml_bytes = f.read()
    patched = patch_declaration(xml_bytes, positions, dividends_year, tax_result, config, TAX_YEAR)
    with open(OUTPUT_XML_PATH, "wb") as f:
        f.write(patched)
    print(f"✓ Збережено: {OUTPUT_XML_PATH}")
    print(f"  Завантажте цей файл на cabinet.tax.gov.ua")
else:
    print(f"⚠ Файл {DECLARATION_XML_PATH} не знайдено.")
    print("  Скачайте декларацію з cabinet.tax.gov.ua і покладіть поруч з notebook.")
```

**Cell 7 — Text instruction:**
```python
from src.report import generate_instruction

instruction = generate_instruction(tax_result, tax_year=TAX_YEAR)
print(instruction)

with open(OUTPUT_TXT_PATH, "w", encoding="utf-8") as f:
    f.write(instruction)
print(f"\n✓ Збережено: {OUTPUT_TXT_PATH}")
```

- [ ] **Step 3: Run the notebook end-to-end**

```bash
jupyter nbconvert --to notebook --execute tax_calculator.ipynb --output tax_calculator_executed.ipynb
```

Expected: executes without errors, `declaration_patched.xml` and `instruction.txt` created.

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 5: Final commit**

```bash
git add tax_calculator.ipynb
git commit -m "feat: add main Jupyter Notebook orchestration"
```

---

## Summary

| Task | Files | Tests |
|------|-------|-------|
| 1. Setup | requirements.txt, config.json | — |
| 2. Parser | src/parser.py | tests/test_parser.py (5) |
| 3. NBU client | src/nbu.py | tests/test_nbu.py (5) |
| 4. FIFO | src/fifo.py | tests/test_fifo.py (5) |
| 5. Tax | src/tax.py | tests/test_tax.py (6) |
| 6. Report | src/report.py | tests/test_report.py (2) |
| 7. Schema research | docs/F0111306.xsd, docs/f1_schema_notes.md | — |
| 8. Dividend UAH | src/fifo.py (append) | tests/test_dividend_uah.py (1) |
| 9. XML patcher | src/xml_patcher.py | tests/test_xml_patcher.py (2) |
| 10. Notebook | tax_calculator.ipynb | integration |

**Total: 26 unit tests + 1 integration run**
