from __future__ import annotations

import polars as pl


def forward_returns(
    df: pl.DataFrame,
    *,
    price_col: str = "last",
    horizon_minutes: int = 60,
) -> pl.DataFrame:
    """
    Compute forward returns over a horizon in minutes.

    Assumes df has columns: ts (Datetime), price_col.
    """
    if "ts" not in df.columns or price_col not in df.columns:
        raise ValueError("df must include 'ts' and price_col")

    horizon = pl.duration(minutes=horizon_minutes)

    out = df.sort("ts").with_columns(
        [
            pl.col(price_col).alias("price"),
            (pl.col(price_col) / pl.col(price_col).shift(-1) - 1).alias("ret_1tick"),
        ]
    )

    # Forward return: price(t+h)/price(t) - 1
    out = out.join_asof(
        out.select(["ts", "price"]).rename({"ts": "ts_fwd", "price": "price_fwd"}),
        left_on="ts",
        right_on="ts_fwd",
        strategy="forward",
        tolerance=horizon,
    ).with_columns((pl.col("price_fwd") / pl.col("price") - 1).alias("ret_fwd"))

    return out
