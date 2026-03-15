# Tax Calculator — Design Spec
**Date:** 2026-03-13
**Status:** Approved

## Overview

A local Jupyter Notebook tool for calculating Ukrainian investment taxes from a Freedom24 (tradernet.com) broker report and patching the user's existing tax declaration XML downloaded from `cabinet.tax.gov.ua`.

**Reference:** osa.tax — analogous commercial service.

---

## Goals

- Parse Freedom24 JSON export (full account history)
- Calculate investment profit using FIFO method (ПКУ ст. 170.2)
- Convert all amounts to UAH using NBU rates on trade date
- Calculate ПДФО (18%) and ВЗ (5% from 2024, 1.5% before) per income type
- Patch existing XML declaration downloaded from cabinet.tax.gov.ua with investment data (додаток Ф1)
- Provide a plain-text instruction listing exact numbers and fields for manual entry (fallback)

---

## Scope

- **Broker:** Freedom24 only (tradernet.com JSON export)
- **Income types:** Investment profit (buy/sell trades) and dividends from foreign securities
- **Interface:** Jupyter Notebook (interactive, run step by step)
- **Tax year:** User specifies the year; full history is used for FIFO cost basis

---

## Project Structure

```
tax/
├── tax_calculator.ipynb     ← main notebook (user runs this)
├── config.json              ← personal data: ПІБ, ІПН, address (filled once)
├── src/
│   ├── parser.py            ← reads Freedom24 JSON, returns normalized transactions
│   ├── nbu.py               ← fetches NBU exchange rates with local caching
│   ├── fifo.py              ← FIFO cost basis and profit calculation
│   ├── tax.py               ← ПДФО + ВЗ calculation by year and income type
│   ├── xml_patcher.py       ← reads existing declaration XML, injects Ф1 appendix
│   └── report.py            ← generates plain-text instruction with amounts and field names
└── cache/
    └── nbu_rates.json       ← cached NBU rates (avoids redundant API calls)
```

---

## Notebook Flow (cells)

1. **Config cell** — set `FREEDOM_JSON_PATH`, `DECLARATION_XML_PATH`, `TAX_YEAR`
2. **Parse** — load Freedom JSON, display summary (total trades, dividends count, date range)
3. **FIFO table** — display all closed positions for `TAX_YEAR` with cost basis, proceeds, profit in USD and UAH
4. **Dividends table** — display dividends received in `TAX_YEAR` with UAH amounts
5. **Tax summary** — display total: investment profit, dividend income, ПДФО, ВЗ
6. **Patch XML** — load existing declaration XML, inject Ф1 appendix, save as `declaration_patched.xml`
7. **Text instruction** — display and save `instruction.txt` with exact field names and amounts for manual entry fallback

---

## Data Flow

### Input: Freedom24 JSON
- `trades.detailed` — buy/sell trades: `trade_id`, `date`, `operation` (buy/sell), `instr_nm` (ticker), `isin`, `p` (price), `q` (quantity), `summ`, `curr_c` (currency), `commission`, `commission_currency`
- `cash_flows.detailed` — filter `type_id == "dividend"`: `date`, `amount`, `currency`, `comment`
  - Company name is extracted from `comment` field using pattern: `"Dividends on security (Company Name (TICKER.EXCHANGE))"`. If parsing fails (empty or unrecognized comment), use `"Unknown"` as company name — this is non-blocking for tax calculation.

### NBU Exchange Rates
- API: `https://bank.gov.ua/NBU_Exchange/exchange_site?start=YYYYMMDD&end=YYYYMMDD&valcode=USD&json`
- Response field: `rate` (UAH per 1 unit of currency)
- Fetch per trade date and cache in `cache/nbu_rates.json` as `{currency: {date: rate}}`
- Supported currencies: USD and EUR (both present in Freedom24 data)
- Rate used: NBU rate on the **settlement date** (`pay_d` field) for trade profit; on the **accrual date** for dividends
- **Weekend/holiday fallback:** if no rate exists for a date, use the most recent prior business day's rate (walk backwards up to 5 days)
- **API failure fallback:** raise a clear error with the date and currency, halt execution

### FIFO Calculation
- Per ticker, maintain a queue of buy lots: `(date, quantity, price, currency, nbu_rate_at_buy_date, commission_usd, commission_nbu_rate)`
- All commissions are in USD regardless of trade currency (`commission_currency` field is always USD in Freedom24 data)
- On sale: deduct from oldest lots first (FIFO)
- Profit per lot (UAH):
  ```
  proceeds_uah = sale_price * qty * nbu_rate_on_settlement_date
  cost_uah = buy_price * qty * nbu_rate_on_buy_settlement_date
  buy_commission_uah = (buy_commission * qty / buy_total_qty) * nbu_rate_on_buy_settlement_date
  sell_commission_uah = (sell_commission * qty / sell_total_qty) * nbu_rate_on_sell_settlement_date
  profit_uah = proceeds_uah - cost_uah - buy_commission_uah - sell_commission_uah
  ```
- Buy commissions are converted at **buy settlement date** rate; sell commissions at **sell settlement date** rate
- **FIFO queue exhausted:** if a sell has no matching buy (impossible for this account since the file starts from account opening date 2024-11-12), raise an error identifying the ticker

### Loss Handling (ПКУ ст. 170.2)
- Losses within the tax year offset gains within the same year
- If net result is negative → tax = 0; losses do **not** carry forward to next year

### Tax Rates by Year
| Period | ПДФО | ВЗ |
|--------|------|----|
| Before 2024-12-01 | 18% | 1.5% |
| 2024-12-01 and after | 18% | 5% |

The ВЗ rate change to 5% applies per the wartime legislation effective **2024-12-01**. Trades settled before this date use 1.5%, trades settled on or after use 5%. Each trade is evaluated individually by `pay_d` date.

Dividends from non-residents: same rates (18% ПДФО + ВЗ), separate line in Ф1.

---

## XML Patching

**Input:** existing `declaration.xml` downloaded from cabinet.tax.gov.ua (contains salary/other income already filled in)

**Note on XML structure:** The exact XSD schema for додаток Ф1 (form `F0111306`) must be fetched from `https://tax.gov.ua` electronic reporting registry before implementing `xml_patcher.py`. The implementation step includes a research sub-task to obtain and document the schema. The spec below describes the logical approach; exact element names come from the XSD.

**Action:**
1. Parse declaration XML using `lxml`
2. Search for existing Ф1 appendix node (`F0111306`):
   - **If found:** overwrite it entirely (do not merge — recalculating always produces a clean result)
   - **If not found:** create a new appendix node and attach it to the declaration root
3. Populate Ф1 rows:
   - One row per closed position (ticker, ISIN, buy date, sell date, proceeds UAH, cost UAH, profit UAH)
   - One row per dividend (company name, accrual date, amount UAH)
   - Totals: investment profit, dividend income, ПДФО amount, ВЗ amount
4. Populate taxpayer identity block from `config.json` (`last_name`, `first_name`, `middle_name`, `tax_id`, `address`)
5. Validate output against the Ф1 XSD schema; raise an error with field details if validation fails
6. Save as `declaration_patched.xml`

**Output:** `declaration_patched.xml` — schema-validated, ready to upload back to cabinet.tax.gov.ua

---

## Text Instruction (Fallback)

`instruction.txt` lists:
- Total investment profit (UAH)
- Total dividend income (UAH)
- ПДФО to pay (UAH)
- ВЗ to pay (UAH)
- Which fields to fill in the online form at cabinet.tax.gov.ua (field names/codes)

---

## Config File

`config.json` (filled once by user):
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

---

## Out of Scope

- Interactive Brokers or other brokers
- Corporate accounts
- Cryptocurrency
- Web UI or CLI interface
- Multi-user support
