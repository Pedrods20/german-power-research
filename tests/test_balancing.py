"""Balancing capacity results and the market a battery commits to each day."""

from __future__ import annotations

import datetime as dt
import io

import openpyxl
import polars as pl
import pytest

from gpa.revenue_stack import revenue_stack
from gpa.sources.base import SourceError
from gpa.sources.regelleistung import parse_capacity_results

DAY = dt.date(2024, 6, 2)


def _workbook(columns: list[str], rows: list[list[object]]) -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    assert sheet is not None
    for row in [columns, *rows]:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_fcr_is_priced_per_hour_and_an_unpriced_second_tender_is_dropped():
    """The 2020 layout: ``DE_`` prefix, EUR/MW per four-hour block, and a blank tender."""
    stamp = dt.datetime.combine(DAY, dt.time())
    columns = ["DATE_FROM", "TENDER_NUMBER", "PRODUCTNAME", "DE_SETTLEMENTCAPACITY_PRICE_[EUR/MW]"]
    rows = [
        [stamp, tender, f"NEGPOS_{h:02d}_{h + 4:02d}", price]
        for h in range(0, 24, 4)
        for tender, price in ((1, "40"), (2, "-"))
    ]
    result = parse_capacity_results(_workbook(columns, rows), "FCR")
    assert result.height == 6
    assert result["product"].unique().to_list() == ["FCR"]
    assert result["price_eur_mw_h"].to_list() == [10.0] * 6
    assert result["block_start_hour"].to_list() == [0, 4, 8, 12, 16, 20]


def test_afrr_reads_both_directions_and_rejects_a_workbook_without_a_german_price():
    stamp = dt.datetime.combine(DAY, dt.time())
    columns = ["DATE_FROM", "PRODUCT", "GERMANY_AVERAGE_CAPACITY_PRICE_[(EUR/MW)/h]"]
    rows = [[stamp, f"{side}_00_04", price] for side, price in (("POS", 3.0), ("NEG", 5.0))]
    result = parse_capacity_results(_workbook(columns, rows), "aFRR")
    assert dict(zip(result["product"], result["price_eur_mw_h"], strict=True)) == {
        "aFRR_POS": 3.0,
        "aFRR_NEG": 5.0,
    }
    # A day the platform has not yet published comes back as an empty sheet.
    assert parse_capacity_results(_workbook([], []), "aFRR").is_empty()
    with pytest.raises(SourceError, match="German aFRR price"):
        parse_capacity_results(_workbook(["DATE_FROM", "PRODUCT"], [[stamp, "POS_00_04"]]), "aFRR")


def _balancing(prices: dict[dt.date, tuple[float, float]]) -> pl.DataFrame:
    """Flat FCR and aFRR prices per day, EUR/MW/h, over every block."""
    rows = [
        {
            "delivery_date": day,
            "product": product,
            "block_start_hour": hour,
            "price_eur_mw_h": value,
            "source": "test",
        }
        for day, (fcr, afrr) in prices.items()
        for hour in range(0, 24, 4)
        for product, value in (("FCR", fcr), ("aFRR_POS", afrr), ("aFRR_NEG", afrr))
    ]
    return pl.DataFrame(rows, schema_overrides={"block_start_hour": pl.Int8})


def _day_ahead(margins: dict[dt.date, float], expected: dict[dt.date, float]):
    """Daily margins for Ridge and perfect foresight, and a one-row dispatch per day."""
    daily = pl.DataFrame(
        [
            {
                "strategy": name,
                "power_mw": 1.0,
                "energy_mwh": 4.0,
                "local_date": day,
                "profit_eur": value,
            }
            for day, value in margins.items()
            for name in ("ridge", "perfect_foresight")
        ]
    )
    dispatch = pl.DataFrame(
        [
            {
                "strategy": "ridge",
                "power_mw": 1.0,
                "energy_mwh": 4.0,
                "local_date": day,
                "action_mwh": 1.0,
                "forecast": value,
            }
            for day, value in expected.items()
        ]
    )
    return daily, dispatch


def test_the_commitment_uses_yesterdays_balancing_prices_never_todays():
    days = [DAY + dt.timedelta(days=i) for i in range(3)]
    # FCR pays 24 EUR/MW/day on day 0, then 240: known only the day after.
    prices = {days[0]: (1.0, 0.0), days[1]: (10.0, 0.0), days[2]: (10.0, 0.0)}
    daily, dispatch = _day_ahead({d: 100.0 for d in days}, {d: 100.0 for d in days})
    result = revenue_stack(daily, dispatch, _balancing(prices)).filter(pl.col("year") == "all")
    value = {row["market"]: row for row in result.to_dicts()}
    # Day 1 commits on day 0's FCR price (24 < 100): day-ahead. Day 2 on day 1's (240): FCR.
    assert value["day_ahead"]["rule_days"] == 1
    assert value["fcr"]["rule_days"] == 1
    assert value["ex_ante_rule"]["eur_per_mw_day"] == pytest.approx((100.0 + 240.0) / 2)
    assert value["hindsight_best"]["eur_per_mw_day"] == pytest.approx(240.0)
    # Raising today's FCR price cannot change today's choice.
    later = {**prices, days[2]: (1_000.0, 0.0)}
    again = revenue_stack(daily, dispatch, _balancing(later)).filter(pl.col("year") == "all")
    assert again.filter(pl.col("market") == "fcr")["rule_days"].item() == 1
