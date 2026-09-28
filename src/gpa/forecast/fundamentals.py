"""Day-ahead operator forecasts of load, wind and solar: the labelled ablation input.

Each row is treated as public at its own D-1 noon gate. The provider records no
publication time, and wind and solar in fact appear hours after the gate, so the
ablation's gain is an upper bound for a forecast read from this source.
"""

from __future__ import annotations

from typing import Final

import polars as pl

from gpa.calendar import attach_local_time
from gpa.zones import Zone

__all__ = ["FUNDAMENTAL_FEATURES", "attach", "from_store"]

FUNDAMENTAL_FEATURES: Final = (
    "da_load_forecast",
    "da_wind_forecast",
    "da_solar_forecast",
    "da_residual_load_forecast",
)
_SERIES = ("load", "wind", "solar")


def from_store(zone: Zone) -> pl.DataFrame:
    """One row per market clock hour and a column per series; partial hours are dropped."""
    from gpa import store

    hourly = (
        store.read("fundamentals", zone.code)
        .group_by("zone", pl.col("ts_utc").dt.truncate("1h"), "series")
        .agg(
            (pl.col("forecast_mw") * pl.col("resolution_min")).sum()
            / pl.col("resolution_min").sum(),
            pl.col("resolution_min").sum().alias("_minutes"),
        )
        .filter(pl.col("_minutes") == 60)
        .pivot(on="series", index=["zone", "ts_utc"], values="forecast_mw")
    )
    hourly = hourly.with_columns(
        pl.lit(None, dtype=pl.Float64).alias(s) for s in _SERIES if s not in hourly.columns
    )
    return (
        attach_local_time(hourly, zone)
        # The repeated autumn clock hour holds two UTC hours: average them, as the target does.
        .group_by("zone", "local_date", "local_hour")
        .agg(pl.col(_SERIES).mean())
    )


def attach(panel: pl.DataFrame, fundamentals: pl.DataFrame) -> pl.DataFrame:
    """Each panel hour's forecasts and the residual load they imply."""
    load, wind, solar = (pl.col(s) for s in _SERIES)
    return panel.join(
        fundamentals.select(
            "local_date",
            "local_hour",
            load.alias("da_load_forecast"),
            wind.alias("da_wind_forecast"),
            solar.alias("da_solar_forecast"),
            (load - wind - solar).alias("da_residual_load_forecast"),
        ),
        on=["local_date", "local_hour"],
        how="left",
    )
