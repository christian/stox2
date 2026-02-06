from __future__ import annotations

from pathlib import Path
import polars as pl

from .config import get_paths


def normalize_ticks(df: pl.DataFrame, symbol: str) -> pl.DataFrame:
    if "ts" not in df.columns:
        raise ValueError("expected a 'ts' column with timestamps")

    out = df.with_columns(
        [
            pl.col("ts").cast(pl.Datetime),
            pl.lit(symbol.upper()).alias("symbol"),
        ]
    )
    return out


def write_ticks(
    df: pl.DataFrame,
    symbol: str,
    *,
    source: str = "ib",
    dataset: str = "ticks",
) -> Path:
    paths = get_paths()
    dataset_path = paths.raw / dataset / f"source={source}"
    dataset_path.mkdir(parents=True, exist_ok=True)

    normalized = normalize_ticks(df, symbol)
    with_date = normalized.with_columns(pl.col("ts").dt.date().alias("date"))

    # Partition by symbol/date for fast selective reads.
    with_date.write_parquet(
        dataset_path,
        partition_by=["symbol", "date"],
    )

    return dataset_path
