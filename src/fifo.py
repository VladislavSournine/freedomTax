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


def enrich_dividends_with_uah(dividends: list, nbu_client) -> list:
    """Add amount_uah field to each dividend using NBU rate on accrual date."""
    result = []
    for div in dividends:
        rate = nbu_client.get_rate(div["currency"], div["date"])
        result.append({**div, "amount_uah": round(div["amount"] * rate, 2)})
    return result


def enrich_other_income_with_uah(other_income: list, nbu_client) -> list:
    """Add amount_uah field to each other-income entry using NBU rate on date."""
    result = []
    for item in other_income:
        rate = nbu_client.get_rate(item["currency"], item["date"])
        result.append({**item, "amount_uah": round(item["amount"] * rate, 2)})
    return result


def enrich_withholding_taxes_with_uah(withholding_taxes: list, nbu_client) -> list:
    """Add amount_uah to each US withholding tax entry (credit against Ukrainian ПДФО)."""
    result = []
    for item in withholding_taxes:
        rate = nbu_client.get_rate(item["currency"], item["date"])
        result.append({**item, "amount_uah": round(item["amount"] * rate, 2)})
    return result
