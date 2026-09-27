"""Day-ahead arbitrage against balancing capacity: which market paid a 1 MW battery more.

Capacity revenue only. FCR is one symmetric megawatt all day and aFRR a positive plus
a negative megawatt; activation energy, state-of-charge management and prequalification
are not modelled. The ex-ante rule commits each day on what is known before the
balancing auctions close at 08:00 on D-1: the previous day's balancing prices, and the
margin the day-ahead schedule expects from its own forecast, whose inputs all predate it.
"""

from __future__ import annotations

from typing import Final

import polars as pl

__all__ = ["MARKETS", "revenue_stack"]

MARKETS: Final = ("day_ahead", "fcr", "afrr")
_BLOCK_HOURS: Final = 4.0
_BLOCKS: Final = {"FCR": 6, "aFRR": 12}
"""A complete day: six four-hour FCR blocks, and six each way for aFRR."""
_SCHEMA: Final = pl.Schema(
    {
        "energy_mwh": pl.Float64(),
        "year": pl.String(),
        "market": pl.String(),
        "days": pl.UInt32(),
        "eur_per_mw_day": pl.Float64(),
        "rule_days": pl.UInt32(),
    }
)


def _balancing_daily(balancing: pl.DataFrame) -> pl.DataFrame:
    """EUR per MW per delivery day, on days where every block of both products cleared."""
    market = pl.col("product").str.head(4).alias("market")
    return (
        balancing.group_by("delivery_date", market)
        .agg((pl.col("price_eur_mw_h") * _BLOCK_HOURS).sum().alias("revenue"), pl.len())
        .filter(pl.col("len") == pl.col("market").replace_strict(_BLOCKS, return_dtype=pl.UInt32))
        .pivot(on="market", index="delivery_date", values="revenue")
        .select(pl.col("delivery_date").alias("local_date"), fcr="FCR", afrr="aFRR")
        .drop_nulls()
    )


def revenue_stack(
    daily: pl.DataFrame,
    dispatch: pl.DataFrame,
    balancing: pl.DataFrame,
    *,
    strategy: str = "ridge",
) -> pl.DataFrame:
    """EUR per MW per day by market and year, with the days the ex-ante rule chose each.

    ``hindsight_best`` takes the best realised market each day and is a ceiling, not a
    strategy; ``ex_ante_rule`` is what the commitment rule above actually earned.
    """
    keys = ["energy_mwh", "local_date"]
    balance = _balancing_daily(balancing) if not balancing.is_empty() else None
    if balance is None or balance.is_empty():
        return pl.DataFrame(schema=_SCHEMA)
    known = balance.select(
        pl.col("local_date") + pl.duration(days=1), fcr_known="fcr", afrr_known="afrr"
    )
    expected = (
        dispatch.filter(pl.col("strategy") == strategy)
        .group_by(keys)
        .agg(
            ((pl.col("action_mwh") * pl.col("forecast")).sum() / pl.col("power_mw").first()).alias(
                "expected"
            )
        )
    )
    days = (
        daily.filter(pl.col("strategy").is_in([strategy, "perfect_foresight"]))
        .with_columns(pl.col("profit_eur") / pl.col("power_mw"))
        .pivot(on="strategy", index=keys, values="profit_eur")
        .rename({strategy: "day_ahead", "perfect_foresight": "day_ahead_perfect"})
        .join(expected, on=keys)
        .join(balance, on="local_date")
        .join(known, on="local_date")
    )
    choice = (
        pl.when(pl.col("expected") >= pl.max_horizontal("fcr_known", "afrr_known"))
        .then(pl.lit("day_ahead"))
        .when(pl.col("fcr_known") >= pl.col("afrr_known"))
        .then(pl.lit("fcr"))
        .otherwise(pl.lit("afrr"))
    )
    days = days.with_columns(choice.alias("choice")).with_columns(
        hindsight_best=pl.max_horizontal(*MARKETS),
        ex_ante_rule=pl.coalesce(
            [pl.when(pl.col("choice") == market).then(pl.col(market)) for market in MARKETS]
        ),
    )
    long = days.with_columns(year=pl.col("local_date").dt.year().cast(pl.String)).unpivot(
        on=[*MARKETS, "day_ahead_perfect", "hindsight_best", "ex_ante_rule"],
        index=["energy_mwh", "year", "choice"],
        variable_name="market",
        value_name="eur_mw",
    )
    periods = [long, long.with_columns(year=pl.lit("all"))]
    return (
        pl.concat(
            period.group_by("energy_mwh", "year", "market").agg(
                pl.len().cast(pl.UInt32).alias("days"),
                pl.col("eur_mw").mean().alias("eur_per_mw_day"),
                (pl.col("choice") == pl.col("market")).sum().cast(pl.UInt32).alias("rule_days"),
            )
            for period in periods
        )
        .with_columns(
            pl.when(pl.col("market").is_in(MARKETS)).then(pl.col("rule_days")).alias("rule_days")
        )
        .select(list(_SCHEMA))
        .sort("energy_mwh", "year", "market")
    )
