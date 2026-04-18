import pytest
from src.tax import aggregate_drfo_oznakas, calculate_taxes, VZ_RATE_CHANGE_DATE


def test_vz_rate_before_cutoff():
    # Trades settled before 2024-12-01 → ВЗ 1.5%
    positions = [
        {"profit_uah": 10000.0, "sell_settlement_date": "2024-11-30",
         "proceeds_uah": 50000, "cost_uah": 40000,
         "buy_commission_uah": 0, "sell_commission_uah": 0}
    ]
    result = calculate_taxes(positions, dividends=[], tax_year=2024)
    assert abs(result["vz_total"] - 150.0) < 0.01  # 10000 * 1.5%


def test_vz_rate_year_2025():
    # tax_year 2025 → ВЗ 5% regardless of settlement date
    positions = [
        {"profit_uah": 10000.0, "sell_settlement_date": "2025-01-15",
         "proceeds_uah": 50000, "cost_uah": 40000,
         "buy_commission_uah": 0, "sell_commission_uah": 0}
    ]
    result = calculate_taxes(positions, dividends=[], tax_year=2025)
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
    # Net = 6000, ПДФО = 1080, ВЗ = 90 (1.5% year rate for 2024)
    assert abs(result["net_profit_uah"] - 6000.0) < 0.01
    assert abs(result["pdfo_total"] - 1080.0) < 0.01
    assert abs(result["vz_trades"] - 90.0) < 0.01  # 6000 * 1.5% (year rate 2024)


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
    # Net = 3000; year rate 2024 = 1.5% → ВЗ = 45
    assert abs(result["net_profit_uah"] - 3000.0) < 0.01
    assert abs(result["vz_trades"] - 45.0) < 0.01  # 3000 * 1.5%


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
    assert abs(result["vz_dividends"] - 7.5) < 0.01      # 500 * 1.5% (year rate 2024)


def test_drfo_aggregates_empty():
    result = aggregate_drfo_oznakas()
    assert result["row_10_13_income"] == 0.0
    assert result["row_11_3_income"] == 0.0
    assert result["has_drfo"] is False


def test_drfo_aggregates_real_numbers():
    # Fixture mirrors Vlad's F1419104 for 2025.
    result = aggregate_drfo_oznakas(
        oznaka_126_income=1409.52, oznaka_126_pdfo_withheld=253.72, oznaka_126_vz_withheld=70.49,
        oznaka_127_income=4348.40, oznaka_127_pdfo_withheld=782.71, oznaka_127_vz_withheld=217.42,
        oznaka_125_income=13166.25,
        oznaka_160_income=5133.50,
    )
    assert abs(result["row_10_13_income"] - 5757.92) < 0.01      # 1409.52 + 4348.40
    assert abs(result["row_10_13_pdfo_withheld"] - 1036.43) < 0.01
    assert abs(result["row_10_13_vz_withheld"] - 287.91) < 0.01
    assert abs(result["row_11_3_income"] - 18299.75) < 0.01      # 13166.25 + 5133.50
    assert result["has_drfo"] is True


def test_drfo_aggregates_only_non_taxable():
    # Only ознака 125 → row 11.3 populated, row 10.13 empty but has_drfo=True.
    result = aggregate_drfo_oznakas(oznaka_125_income=500.0)
    assert result["row_10_13_income"] == 0.0
    assert result["row_11_3_income"] == 500.0
    assert result["has_drfo"] is True
