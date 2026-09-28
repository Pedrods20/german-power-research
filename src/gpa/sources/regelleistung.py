"""German balancing capacity auction results from regelleistung.net, the TSOs' platform.

Public and without credentials: one workbook per delivery day and product. Only the
German result is read. Its column prefix changed from ``DE_`` to ``GERMANY_`` and the
aFRR unit from EUR/MW per block to EUR/MW per hour, so both are matched by name.
"""

from __future__ import annotations

import datetime as dt
import io
import re
from typing import Final

import httpx
import polars as pl

from gpa.reference import BALANCING_SCHEMA
from gpa.sources.base import SourceError, fetch_bytes

__all__ = ["PRODUCTS", "fetch_capacity_results", "parse_capacity_results"]

PRODUCTS: Final = ("FCR", "aFRR")

_URL: Final = (
    "https://www.regelleistung.net/apps/cpp-publisher/api/v1/download/tenders/resultsoverview"
)
_BLOCK_HOURS: Final = 4.0
_PRICE: Final = {
    # FCR clears at one uniform price; aFRR is pay-as-bid, so its average is a proxy.
    "FCR": re.compile(r"^(?:DE|GERMANY)_SETTLEMENTCAPACITY_PRICE_\[(EUR/MW)\]$"),
    "aFRR": re.compile(r"^(?:DE|GERMANY)_AVERAGE_CAPACITY_PRICE_\[(EUR/MW|\(EUR/MW\)/h)\]$"),
}
_BLOCK: Final = re.compile(r"^(NEGPOS|POS|NEG)_(\d{2})_(\d{2})$")


def parse_capacity_results(workbook: bytes, product: str) -> pl.DataFrame:
    """One row per German four-hour block, priced in EUR per MW per hour."""
    frame = pl.read_excel(io.BytesIO(workbook), engine="openpyxl", raise_if_empty=False)
    if frame.is_empty():
        return pl.DataFrame(schema=BALANCING_SCHEMA)
    matches = [(name, found) for name in frame.columns if (found := _PRICE[product].match(name))]
    if len(matches) != 1:
        raise SourceError(f"expected one German {product} price column, got {frame.columns}")
    column, found = matches[0]
    per_hour = 1.0 if found.group(1).endswith("/h") else 1.0 / _BLOCK_HOURS
    label = pl.col("PRODUCTNAME" if "PRODUCTNAME" in frame.columns else "PRODUCT")
    direction = label.str.extract(_BLOCK.pattern, 1)
    parsed = frame.select(
        pl.col("DATE_FROM").cast(pl.Date).alias("delivery_date"),
        pl.when(direction == "NEGPOS")
        .then(pl.lit("FCR"))
        .otherwise(pl.lit("aFRR_") + direction)
        .alias("product"),
        label.str.extract(_BLOCK.pattern, 2).cast(pl.Int8).alias("block_start_hour"),
        # An unpriced block reads "-": it stays missing, never zero.
        (pl.col(column).cast(pl.Float64, strict=False) * per_hour).alias("price_eur_mw_h"),
        pl.lit("regelleistung.net").alias("source"),
        (pl.col("TENDER_NUMBER") if "TENDER_NUMBER" in frame.columns else pl.lit(1)).alias(
            "_tender"
        ),
    )
    if parsed.select("product", "block_start_hour").null_count().sum_horizontal().item():
        raise SourceError(f"unexpected {product} block names in {frame.columns}")
    # Some days list a second, unpriced tender; the first priced one is the day's result.
    return (
        parsed.drop_nulls("price_eur_mw_h")
        .sort("_tender")
        .unique(["delivery_date", "product", "block_start_hour"], keep="first", maintain_order=True)
        .drop("_tender")
        .cast(BALANCING_SCHEMA)
    )


def fetch_capacity_results(
    day: dt.date, product: str, *, client: httpx.Client | None = None
) -> pl.DataFrame:
    """The German capacity auction results for one delivery day and product."""
    if product not in PRODUCTS:
        raise ValueError(f"product must be one of {PRODUCTS}, got {product!r}")
    params = {
        "date": day.isoformat(),
        "exportFormat": "xlsx",
        "market": "CAPACITY",
        "productTypes": product,
    }
    return parse_capacity_results(fetch_bytes(_URL, client=client, params=params), product)
