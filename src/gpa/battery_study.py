"""Retrospective battery economics on a common sample, with exploratory uncertainty.

The best naive is picked in-sample, so it is a diagnostic, not a deployable rule;
cost rates are explicit assumptions.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
import polars as pl

from gpa.battery import DEFAULT_MODELS, BatterySpec, SpecKwargs, backtest_predictions, dispatch
from gpa.calendar import attach_local_time
from gpa.reference import QUARTER_HOUR_SCHEMA
from gpa.zones import Zone

BASELINES: Final = DEFAULT_MODELS[:3]
QUARTER_HOUR_START: Final = dt.date(2025, 10, 1)
"""First delivery day of DE-LU's 15-minute day-ahead products."""

_QUARTER_SOC_STEP_MWH: Final = 1 / 64
"""On the hourly 0.25 MWh grid a quarter-hour at 1 MW could not move a single step."""

_SURPRISE_LABELS: Final = ["1 (most typical)", "2", "3", "4", "5 (most atypical)"]
_DISAGREEMENT_LABELS: Final = ["1 (agrees most)", "2", "3", "4", "5 (disagrees most)"]
_KEYS: Final = ["strategy", "power_mw", "energy_mwh"]
_MIN_BLOCKS: Final = 8
_RISK_SCHEMA: Final = {
    "strategy": pl.String,
    "power_mw": pl.Float64,
    "energy_mwh": pl.Float64,
    "days": pl.UInt32,
    "profit_eur": pl.Float64,
    "profit_eur_mw": pl.Float64,
    "worst_day_eur": pl.Float64,
    "loss_days": pl.UInt32,
    "max_drawdown_eur": pl.Float64,
    "worst_observed_month": pl.String,
    "worst_observed_month_eur": pl.Float64,
    "worst_month_observed_days": pl.UInt32,
    "top_5_days_share_positive_margin": pl.Float64,
    "best_naive": pl.String,
    "best_naive_selection": pl.String,
    "incremental_vs_best_naive_eur_mw": pl.Float64,
}
_COMPARISON_SCHEMA: Final = {
    "strategy": pl.String,
    "baseline": pl.String,
    "power_mw": pl.Float64,
    "energy_mwh": pl.Float64,
    "paired_days": pl.UInt32,
    "calendar_blocks": pl.UInt32,
    "block_days": pl.UInt32,
    "incremental_eur_mw": pl.Float64,
    "mean_daily_incremental_eur_mw": pl.Float64,
    "underperform_days": pl.UInt32,
    "top_5_days_share_positive_incremental": pl.Float64,
    "incremental_without_best_5_days_eur_mw": pl.Float64,
    "ci_low_eur_mw": pl.Float64,
    "ci_high_eur_mw": pl.Float64,
    "status": pl.String,
}
_ATTRIBUTION_SCHEMA: Final = pl.Schema(
    {
        "strategy": pl.String(),
        "baseline": pl.String(),
        "power_mw": pl.Float64(),
        "energy_mwh": pl.Float64(),
        "dimension": pl.String(),
        "bucket": pl.String(),
        "days": pl.UInt32(),
        "day_share": pl.Float64(),
        "incremental_eur_mw": pl.Float64(),
        "incremental_share": pl.Float64(),
        "mean_daily_incremental_eur_mw": pl.Float64(),
    }
)


@dataclass(frozen=True, slots=True)
class BatteryStudy:
    dispatch: pl.DataFrame
    summary: pl.DataFrame
    coverage: pl.DataFrame
    daily: pl.DataFrame
    risk: pl.DataFrame
    comparisons: pl.DataFrame


def _validate_daily(daily: pl.DataFrame) -> pl.DataFrame:
    required = {*_KEYS, "local_date", "profit_eur"}
    if missing := required - set(daily.columns):
        raise ValueError(f"daily economics missing columns: {sorted(missing)}")
    ordered = daily.with_columns(pl.col("local_date").cast(pl.Date)).sort([*_KEYS, "local_date"])
    if ordered.select(pl.any_horizontal(pl.col(sorted(required)).is_null()).any()).item():
        raise ValueError("daily economics must be fully settled and labelled")
    if ordered.filter(
        ~pl.all_horizontal(pl.col("profit_eur", "power_mw", "energy_mwh").is_finite())
        | (pl.col("power_mw") <= 0)
        | (pl.col("energy_mwh") <= 0)
    ).height:
        raise ValueError("daily economics must be finite with positive power and capacity")
    if ordered.select(pl.struct([*_KEYS, "local_date"]).is_duplicated().any()).item():
        raise ValueError("duplicate strategy/asset/day economics")
    for asset in ordered.partition_by(["power_mw", "energy_mwh"]):
        dates = [set(model["local_date"]) for model in asset.partition_by("strategy")]
        if any(days != dates[0] for days in dates[1:]):
            raise ValueError("all strategies must use the same complete days")
    return ordered


def _assets(daily: pl.DataFrame) -> Iterator[dict[str, pl.DataFrame]]:
    """Each asset's validated daily margins, keyed by strategy."""
    for asset in _validate_daily(daily).partition_by(["power_mw", "energy_mwh"]):
        yield {part["strategy"][0]: part for part in asset.partition_by("strategy")}


def _best_naive(models: dict[str, pl.DataFrame], baselines: Sequence[str]) -> str | None:
    """The naive with the largest sample margin: picked in hindsight, a diagnostic only."""
    candidates = sorted(name for name in baselines if name in models)
    return max(candidates, key=lambda n: float(models[n]["profit_eur"].sum()), default=None)


def _top_five_share(values: npt.NDArray[np.float64]) -> float | None:
    """Share of the positive total carried by the five best days: ex-post concentration."""
    positive = values[values > 0]
    return float(np.sort(positive)[-5:].sum() / positive.sum()) if positive.size else None


def daily_margins(dispatch: pl.DataFrame) -> pl.DataFrame:
    """Daily settlement and activity; missing settlement is an error, never a zero."""
    if dispatch["profit_eur"].null_count():
        raise ValueError("economic study requires fully settled dispatch")
    money = ("gross_revenue_eur", "operating_cost_eur", "degradation_cost_eur", "profit_eur")
    return (
        dispatch.group_by([*_KEYS, "local_date"])
        .agg(
            pl.len().cast(pl.UInt32).alias("intervals"),
            pl.col("duration_hours").sum().alias("delivery_hours"),
            pl.col(*money, "battery_throughput_mwh").sum(),
        )
        .with_columns(
            (pl.col("battery_throughput_mwh") / (2 * pl.col("energy_mwh"))).alias(
                "equivalent_cycles"
            )
        )
        .sort([*_KEYS, "local_date"])
    )


def risk_metrics(daily: pl.DataFrame, *, baselines: Sequence[str] = BASELINES) -> pl.DataFrame:
    """Observed-sample downside, and the margin over the in-sample best naive.

    Drawdown starts from a zero balance; monthly totals cover observed days only,
    and their day counts are published beside them.
    """
    rows = []
    for models in _assets(daily):
        best = _best_naive(models, baselines)
        for name, frame in models.items():
            values = frame["profit_eur"].to_numpy()
            cumulative = np.r_[0.0, np.cumsum(values)]
            worst = (
                frame.group_by(pl.col("local_date").dt.strftime("%Y-%m").alias("month"))
                .agg(pl.col("profit_eur").sum(), pl.len().alias("days"))
                .sort("profit_eur", "month")
                .row(0, named=True)
            )
            power, profit = float(frame["power_mw"][0]), float(values.sum())
            rows.append(
                {
                    "strategy": name,
                    "power_mw": power,
                    "energy_mwh": float(frame["energy_mwh"][0]),
                    "days": len(values),
                    "profit_eur": profit,
                    "profit_eur_mw": profit / power,
                    "worst_day_eur": float(values.min()),
                    "loss_days": int((values < 0).sum()),
                    "max_drawdown_eur": float(
                        (np.maximum.accumulate(cumulative) - cumulative).max()
                    ),
                    "worst_observed_month": worst["month"],
                    "worst_observed_month_eur": worst["profit_eur"],
                    "worst_month_observed_days": worst["days"],
                    "top_5_days_share_positive_margin": _top_five_share(values),
                    "best_naive": best,
                    "best_naive_selection": "retrospective_in_sample" if best else None,
                    "incremental_vs_best_naive_eur_mw": (
                        (profit - float(models[best]["profit_eur"].sum())) / power if best else None
                    ),
                }
            )
    return pl.DataFrame(rows, schema=_RISK_SCHEMA).sort("energy_mwh", "power_mw", "strategy")


def paired_comparisons(
    daily: pl.DataFrame,
    *,
    baselines: Sequence[str] = BASELINES,
    block_days: int = 7,
    resamples: int = 2000,
    seed: int = 20260914,
) -> pl.DataFrame:
    """Exploratory 95% intervals for each model's paired margin over each naive.

    Non-overlapping calendar blocks from the first sample day are resampled whole,
    missing dates are never imputed, and each resample's daily mean is scaled back to
    the observed length. Eight blocks of eight block-lengths are required. The
    intervals are conditional and uncorrected for multiple comparisons.
    """
    if block_days < 1 or resamples < 100 or seed < 0:
        raise ValueError("block_days >= 1, resamples >= 100 and seed >= 0 are required")
    rows = []
    for models in _assets(daily):
        for baseline in sorted(set(baselines) & set(models)):
            reference = models[baseline]
            dates = reference["local_date"].to_list()
            _, codes = np.unique(
                [(day - dates[0]).days // block_days for day in dates], return_inverse=True
            )
            counts = np.bincount(codes)
            blocks = len(counts)
            for name in sorted(set(models) - set(baselines)):
                frame = models[name]
                power = float(frame["power_mw"][0])
                delta = (
                    frame["profit_eur"].to_numpy() - reference["profit_eur"].to_numpy()
                ) / power
                low: float | None = None
                high: float | None = None
                status = "insufficient_blocks" if blocks < _MIN_BLOCKS else "insufficient_days"
                if blocks >= _MIN_BLOCKS and len(delta) >= _MIN_BLOCKS * block_days:
                    totals = np.bincount(codes, weights=delta)
                    draws = np.random.default_rng(seed).integers(
                        0, blocks, size=(resamples, blocks)
                    )
                    margins = totals[draws].sum(axis=1) / counts[draws].sum(axis=1) * len(delta)
                    low, high = map(float, np.quantile(margins, [0.025, 0.975]))
                    status = "exploratory"
                best_five = np.sort(delta[delta > 0])[-5:].sum()
                rows.append(
                    {
                        "strategy": name,
                        "baseline": baseline,
                        "power_mw": power,
                        "energy_mwh": float(frame["energy_mwh"][0]),
                        "paired_days": len(delta),
                        "calendar_blocks": blocks,
                        "block_days": block_days,
                        "incremental_eur_mw": float(delta.sum()),
                        "mean_daily_incremental_eur_mw": float(delta.mean()),
                        "underperform_days": int((delta < 0).sum()),
                        "top_5_days_share_positive_incremental": _top_five_share(delta),
                        "incremental_without_best_5_days_eur_mw": float(delta.sum() - best_five),
                        "ci_low_eur_mw": low,
                        "ci_high_eur_mw": high,
                        "status": status,
                    }
                )
    return pl.DataFrame(rows, schema=_COMPARISON_SCHEMA).sort(
        "energy_mwh", "power_mw", "strategy", "baseline"
    )


def _either(condition: pl.Expr, yes: str, no: str) -> pl.Expr:
    return pl.when(condition).then(pl.lit(yes)).otherwise(pl.lit(no))


def day_types(predictions: pl.DataFrame, naive: str) -> pl.DataFrame:
    """Each day's labels, from realised prices and the naive's own forecast only.

    Shape surprise ranks days by the rank correlation between the naive's hours and the
    realised ones: quintile 5 holds the days a rule that repeats the shape misread most.
    """
    days = (
        predictions.filter(pl.col("model") == naive)
        .group_by(pl.col("local_date").cast(pl.Date))
        .agg(
            (pl.col("actual") < 0).any().alias("negative"),
            pl.corr("forecast", "actual", method="spearman").fill_nan(None).alias("_rank"),
        )
    )
    return days.select(
        "local_date",
        _either(pl.col("negative"), "Some negative hours", "No negative hours").alias(
            "negative_prices"
        ),
        (-pl.col("_rank"))
        .qcut(5, labels=_SURPRISE_LABELS, allow_duplicates=True)
        .cast(pl.String)
        .fill_null("Undefined")
        .alias("shape_surprise"),
        _either(pl.col("local_date").dt.weekday() >= 6, "Weekend", "Weekday").alias("day_type"),
        pl.format("Q{}", pl.col("local_date").dt.quarter()).alias("quarter"),
    )


def _disagreement(asset: pl.DataFrame, strategy: str, naive: str) -> pl.DataFrame:
    """Quintile of what the model's schedule expected over the naive's, at the model's prices.

    Both schedules and the forecast exist at the gate, so a desk could act on this label.
    """
    naive_actions = asset.filter(pl.col("strategy") == naive).select("ts_utc", naive="action_mwh")
    return (
        asset.filter(pl.col("strategy") == strategy)
        .join(naive_actions, on="ts_utc")
        .group_by("local_date")
        .agg(((pl.col("action_mwh") - pl.col("naive")) * pl.col("forecast")).sum().alias("_gain"))
        .select(
            "local_date",
            pl.col("_gain")
            .qcut(5, labels=_DISAGREEMENT_LABELS, allow_duplicates=True)
            .cast(pl.String)
            .alias("forecast_disagreement"),
        )
    )


def attribution(
    daily: pl.DataFrame,
    predictions: pl.DataFrame,
    dispatch: pl.DataFrame,
    *,
    strategy: str = "ridge",
    baselines: Sequence[str] = BASELINES,
) -> pl.DataFrame:
    """Where a model's margin over the best naive was earned, by day labels fixed in advance.

    A group's share can exceed 100% or turn negative: days where the model lost offset
    the rest.
    """
    frames = []
    for models in _assets(daily):
        best = _best_naive(models, baselines)
        if best is None or strategy not in models:
            continue
        model = models[strategy]
        power, energy = float(model["power_mw"][0]), float(model["energy_mwh"][0])
        asset = dispatch.filter((pl.col("power_mw") == power) & (pl.col("energy_mwh") == energy))
        days = (
            model.select(
                "local_date",
                ((model["profit_eur"] - models[best]["profit_eur"]) / power).alias("incremental"),
            )
            .join(day_types(predictions, best), on="local_date", how="left")
            .join(_disagreement(asset, strategy, best), on="local_date", how="left")
        )
        total = float(days["incremental"].sum())
        for dimension in (
            "negative_prices",
            "shape_surprise",
            "forecast_disagreement",
            "day_type",
            "quarter",
        ):
            frames.append(
                days.group_by(pl.col(dimension).alias("bucket"))
                .agg(
                    pl.len().cast(pl.UInt32).alias("days"),
                    pl.col("incremental").sum().alias("incremental_eur_mw"),
                )
                .with_columns(
                    strategy=pl.lit(strategy),
                    baseline=pl.lit(best),
                    power_mw=pl.lit(power),
                    energy_mwh=pl.lit(energy),
                    dimension=pl.lit(dimension),
                    day_share=pl.col("days") / days.height,
                    incremental_share=pl.col("incremental_eur_mw") / total,
                    mean_daily_incremental_eur_mw=pl.col("incremental_eur_mw") / pl.col("days"),
                )
            )
    if not frames:
        return pl.DataFrame(schema=_ATTRIBUTION_SCHEMA)
    return (
        pl.concat(frames)
        .select(list(_ATTRIBUTION_SCHEMA))
        .cast(_ATTRIBUTION_SCHEMA)
        .sort("energy_mwh", "strategy", "dimension", "bucket")
    )


def quarter_hour_value(
    prices: pl.DataFrame, zone: Zone, *, durations_mwh: Sequence[float] = (1.0, 2.0, 4.0)
) -> pl.DataFrame:
    """What trading quarter-hours instead of hours is worth to the same battery.

    Both cases dispatch quarter-hours on one SOC grid and differ only in price: each
    quarter-hour's own, or its hour's average, which a flat hourly trade settles at.
    Perfect foresight is the ceiling and repeating the previous day the simple rule. Only
    96-interval days after a 96-interval day are used, so clock-change days drop out.
    """
    local = attach_local_time(prices.filter(pl.col("resolution_min") == 15), zone).filter(
        pl.col("local_date") >= QUARTER_HOUR_START
    )
    full = local.group_by("local_date").len().filter(pl.col("len") == 96)["local_date"]
    frame = (
        local.filter(pl.col("local_date").is_in(full.to_list()))
        .sort("ts_utc")
        .with_columns(
            pl.int_range(pl.len()).over("local_date").alias("slot"),
            pl.col("price").mean().over("local_date", "local_hour").alias("hourly"),
        )
    )
    previous = frame.select(
        pl.col("local_date") + pl.duration(days=1),
        "slot",
        pl.col("price").alias("previous_price"),
        pl.col("hourly").alias("previous_hourly"),
    )
    frame = frame.join(previous, on=["local_date", "slot"])
    if frame.is_empty():
        return pl.DataFrame(schema=QUARTER_HOUR_SCHEMA)
    start, end = frame["local_date"].min(), frame["local_date"].max()
    rows = []
    for size in durations_mwh:
        spec = BatterySpec(energy_mwh=float(size), soc_step_mwh=_QUARTER_SOC_STEP_MWH)
        for resolution, actual, naive in (
            ("quarter_hour", "price", "previous_price"),
            ("hourly", "hourly", "previous_hourly"),
        ):
            for strategy, forecast in (
                ("perfect_foresight", actual),
                ("naive_previous_day", naive),
            ):
                settled = dispatch(
                    frame.select(
                        "ts_utc",
                        "local_date",
                        "local_hour",
                        pl.lit(0.25).alias("duration_hours"),
                        pl.col(forecast).alias("forecast"),
                        pl.col(actual).alias("actual"),
                    ),
                    spec,
                    strategy=strategy,
                    timezone=zone.timezone,
                )
                days, profit = settled["local_date"].n_unique(), float(settled["profit_eur"].sum())
                rows.append(
                    {
                        "strategy": strategy,
                        "resolution": resolution,
                        "power_mw": spec.power_mw,
                        "energy_mwh": spec.energy_mwh,
                        "days": days,
                        "profit_eur": profit,
                        "eur_per_mw_day": profit / spec.power_mw / days,
                        "sample_start": start,
                        "sample_end": end,
                    }
                )
    return pl.DataFrame(rows, schema=QUARTER_HOUR_SCHEMA)


def evaluate(
    predictions: pl.DataFrame,
    *,
    model_names: Sequence[str] = DEFAULT_MODELS,
    durations_mwh: Sequence[float] = (1.0, 2.0, 4.0),
    spec_kwargs: SpecKwargs | None = None,
    block_days: int = 7,
    resamples: int = 2000,
    seed: int = 20260914,
) -> BatteryStudy:
    """Run a DE-LU study from supplied retrospective predictions, without IO."""
    if "zone" in predictions.columns and set(predictions["zone"].unique().to_list()) != {"DE-LU"}:
        raise ValueError("this study requires a single DE-LU prediction sample")
    result = backtest_predictions(
        predictions, model_names=model_names, durations_mwh=durations_mwh, spec_kwargs=spec_kwargs
    )
    if result.dispatch.is_empty():
        raise ValueError("no shared complete settled days; inspect input coverage first")
    daily = daily_margins(result.dispatch)
    return BatteryStudy(
        result.dispatch,
        result.summary,
        result.coverage,
        daily,
        risk_metrics(daily),
        paired_comparisons(daily, block_days=block_days, resamples=resamples, seed=seed),
    )
