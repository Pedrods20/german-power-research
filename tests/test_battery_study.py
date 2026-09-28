"""Economic interpretation and paired uncertainty on a common sample."""

import datetime as dt

import polars as pl
import pytest

from gpa.battery_study import (
    attribution,
    evaluate,
    paired_comparisons,
    quarter_hour_value,
    risk_metrics,
)
from gpa.zones import get_zone
from tests.test_battery import DAY, TZ, predictions


def daily_sample(values, *, baseline=None, days=None):
    dates = days or [DAY + dt.timedelta(days=i) for i in range(len(values))]
    baseline = [0.0] * len(values) if baseline is None else baseline
    rows = []
    for model, profits in (("ridge", values), ("naive_previous_day", baseline)):
        rows.extend(
            {
                "local_date": day,
                "strategy": model,
                "power_mw": 1.0,
                "energy_mwh": 4.0,
                "profit_eur": value,
            }
            for day, value in zip(dates, profits, strict=True)
        )
    return pl.DataFrame(rows)


def test_risk_metrics_include_initial_loss_and_concentration_denominator():
    risk = risk_metrics(daily_sample([-10.0, 20.0, -30.0, 40.0]))
    row = risk.filter(pl.col("strategy") == "ridge").row(0, named=True)
    assert row["profit_eur"] == 20.0
    assert row["worst_day_eur"] == -30.0
    assert row["max_drawdown_eur"] == 30.0
    assert row["loss_days"] == 2
    assert row["top_5_days_share_positive_margin"] == 1.0
    assert row["worst_observed_month_eur"] == 20.0
    assert row["worst_month_observed_days"] == 4
    assert row["incremental_vs_best_naive_eur_mw"] == 20.0
    assert row["best_naive_selection"] == "retrospective_in_sample"
    losses = risk_metrics(daily_sample([-10.0, -20.0]))
    assert losses.filter(pl.col("strategy") == "ridge")["max_drawdown_eur"].item() == 30.0
    assert (
        losses.filter(pl.col("strategy") == "ridge")["top_5_days_share_positive_margin"].item()
        is None
    )


def test_pairing_uses_differences_and_is_reproducible():
    baseline = [float(i % 11) for i in range(70)]
    daily = daily_sample([value + 2.0 for value in baseline], baseline=baseline)
    one = paired_comparisons(daily, resamples=200, seed=7)
    two = paired_comparisons(daily.reverse(), resamples=200, seed=7)
    assert one.to_dicts() == two.to_dicts()
    row = one.filter(pl.col("strategy") == "ridge").row(0, named=True)
    assert row["incremental_eur_mw"] == 140.0
    assert row["ci_low_eur_mw"] == pytest.approx(140.0)
    assert row["ci_high_eur_mw"] == pytest.approx(140.0)
    assert row["status"] == "exploratory"
    assert row["underperform_days"] == 0
    assert row["top_5_days_share_positive_incremental"] == pytest.approx(5 / 70)
    assert row["incremental_without_best_5_days_eur_mw"] == 130.0


def test_incremental_concentration_never_divides_by_net_profit():
    row = paired_comparisons(daily_sample([-10.0, 5.0, 5.0])).row(0, named=True)
    assert row["incremental_eur_mw"] == 0.0
    assert row["underperform_days"] == 1
    assert row["top_5_days_share_positive_incremental"] == 1.0
    assert row["incremental_without_best_5_days_eur_mw"] == -10.0
    losses = paired_comparisons(daily_sample([-1.0, -2.0])).row(0, named=True)
    assert losses["top_5_days_share_positive_incremental"] is None
    assert losses["incremental_without_best_5_days_eur_mw"] == -3.0


def test_short_sample_does_not_manufacture_a_confidence_interval():
    result = paired_comparisons(daily_sample([5.0] * 14), resamples=200)
    row = result.filter(pl.col("strategy") == "ridge").row(0, named=True)
    assert row["status"] == "insufficient_blocks"
    assert row["ci_low_eur_mw"] is None


def test_calendar_gaps_are_not_collapsed_into_adjacent_observations():
    dates = [DAY + dt.timedelta(days=7 * i) for i in range(10)]
    result = paired_comparisons(daily_sample([2.0] * 10, days=dates), resamples=200)
    row = result.filter(pl.col("strategy") == "ridge").row(0, named=True)
    assert row["calendar_blocks"] == 10
    assert row["paired_days"] == 10
    assert row["status"] == "insufficient_days"
    assert row["ci_low_eur_mw"] is None


def test_unmatched_days_raise_instead_of_cherry_picking():
    frame = daily_sample([1.0] * 10).filter(
        ~((pl.col("strategy") == "ridge") & (pl.col("local_date") == DAY))
    )
    with pytest.raises(ValueError, match=r"same.*days"):
        paired_comparisons(frame)


def test_evaluation_retains_costs_and_coverage():
    frame = predictions()
    result = evaluate(
        frame,
        durations_mwh=(1.0,),
        spec_kwargs={"variable_cost_eur_mwh": 2.0, "degradation_cost_eur_mwh": 3.0},
        resamples=200,
    )
    assert result.coverage.height == 5
    assert result.daily.height == 7
    assert result.comparisons.height == 12  # four non-naive strategies x three fixed naives
    rows = result.daily.filter(pl.col("strategy") == "ridge")
    assert rows["operating_cost_eur"].item() > 0
    assert rows["profit_eur"].item() == pytest.approx(
        rows["gross_revenue_eur"].item()
        - rows["operating_cost_eur"].item()
        - rows["degradation_cost_eur"].item()
    )


def _shaped_days(count: int) -> pl.DataFrame:
    """The naive's forecast on day ``i`` reverses the first ``2i`` realised hours.

    Rank correlation with the realised day therefore falls day by day, so the first day
    is the most typical and the last the most atypical; the last day also dips below zero.
    """
    rows = []
    for i in range(count):
        actual = [
            float(hour) - (30.0 if i == count - 1 and hour == 0 else 0.0) for hour in range(24)
        ]
        forecast = actual[: 2 * i][::-1] + actual[2 * i :]
        rows += [
            {
                "model": "naive_previous_day",
                "local_date": DAY + dt.timedelta(days=i),
                "local_hour": hour,
                "forecast": forecast[hour],
                "actual": actual[hour],
            }
            for hour in range(24)
        ]
    return pl.DataFrame(rows)


def _schedules(expected: list[float]) -> pl.DataFrame:
    """One interval a day on which the model's schedule expects ``expected[i]`` over the naive's."""
    return pl.DataFrame(
        [
            {
                "strategy": strategy,
                "power_mw": 1.0,
                "energy_mwh": 4.0,
                "local_date": DAY + dt.timedelta(days=i),
                "ts_utc": dt.datetime.combine(DAY + dt.timedelta(days=i), dt.time(), dt.UTC),
                "action_mwh": 1.0 if strategy == "ridge" else 0.0,
                "forecast": value,
            }
            for i, value in enumerate(expected)
            for strategy in ("ridge", "naive_previous_day")
        ]
    )


def test_attribution_splits_the_whole_increment_by_labels_that_ignore_the_model():
    increments = [float(i) for i in range(10)]
    daily = daily_sample([10.0 + x for x in increments], baseline=[10.0] * 10)
    result = attribution(daily, _shaped_days(10), _schedules(increments))
    for dimension in result.partition_by("dimension"):
        assert dimension["incremental_eur_mw"].sum() == pytest.approx(sum(increments))
        assert dimension["days"].sum() == 10
        assert dimension["incremental_share"].sum() == pytest.approx(1.0)
    groups = {
        (row["dimension"], row["bucket"]): row["incremental_eur_mw"]
        for row in result.iter_rows(named=True)
    }
    # Days 0-1 are the most typical and days 8-9 the most atypical.
    assert groups[("shape_surprise", "1 (most typical)")] == pytest.approx(0.0 + 1.0)
    assert groups[("shape_surprise", "5 (most atypical)")] == pytest.approx(8.0 + 9.0)
    assert groups[("negative_prices", "Some negative hours")] == pytest.approx(9.0)
    # 10 February 2025 is a Monday, so the sample holds one weekend.
    assert groups[("day_type", "Weekend")] == pytest.approx(5.0 + 6.0)


def test_forecast_disagreement_ranks_days_by_what_the_model_expected_at_the_gate():
    increments = [float(i) for i in range(10)]
    daily = daily_sample([10.0 + x for x in increments], baseline=[10.0] * 10)
    # The model expected least on the days it went on to earn most.
    result = attribution(daily, _shaped_days(10), _schedules([9.0 - x for x in increments]))
    groups = {
        row["bucket"]: row["incremental_eur_mw"]
        for row in result.filter(pl.col("dimension") == "forecast_disagreement").iter_rows(
            named=True
        )
    }
    assert groups["1 (agrees most)"] == pytest.approx(8.0 + 9.0)
    assert groups["5 (disagrees most)"] == pytest.approx(0.0 + 1.0)


def _quarter_prices(days: int, *, spike: float) -> pl.DataFrame:
    """Quarter-hour prices from 6 October 2025; ``spike`` widens each hour's quarters."""
    start = dt.datetime(2025, 10, 6, tzinfo=TZ).astimezone(dt.UTC)
    stamps = [start + dt.timedelta(minutes=15 * i) for i in range(96 * days)]
    shape = [0.0 if (i // 4) % 24 < 12 else 100.0 for i in range(96 * days)]
    offsets = [(-spike, 0.0, 0.0, spike)[i % 4] for i in range(96 * days)]
    return pl.DataFrame(
        {
            "zone": "DE-LU",
            "ts_utc": stamps,
            "resolution_min": 15,
            "price": [base + offset for base, offset in zip(shape, offsets, strict=True)],
            "currency": "EUR",
            "source": "test",
        },
        schema_overrides={"ts_utc": pl.Datetime("us", "UTC"), "resolution_min": pl.Int16},
    )


def test_quarter_hours_add_nothing_when_each_hour_is_flat_and_value_when_it_is_not():
    zone = get_zone("DE-LU")
    flat = quarter_hour_value(_quarter_prices(3, spike=0.0), zone, durations_mwh=(1.0,))
    assert flat["days"].unique().to_list() == [2]  # the first day has no previous day
    by = {
        (row["strategy"], row["resolution"]): row["profit_eur"]
        for row in flat.iter_rows(named=True)
    }
    for strategy in ("perfect_foresight", "naive_previous_day"):
        assert by[(strategy, "quarter_hour")] == pytest.approx(by[(strategy, "hourly")])
    spiky = quarter_hour_value(_quarter_prices(3, spike=40.0), zone, durations_mwh=(1.0,))
    margin = {
        row["resolution"]: row["profit_eur"]
        for row in spiky.filter(pl.col("strategy") == "perfect_foresight").iter_rows(named=True)
    }
    assert margin["quarter_hour"] > margin["hourly"]
