from __future__ import annotations

from pathlib import Path
import polars as pl

from .config import get_paths


def normalize_ticks(df: pl.DataFrame, symbol: str) -> pl.DataFrame:
    required = {"ts", "last", "size"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")

    out = df.with_columns(
        [
            pl.col("ts").cast(pl.Datetime),
            pl.col("last").cast(pl.Float64),
            pl.col("size"),
            pl.lit(symbol.upper()).alias("symbol"),
        ]
    ).select(["ts", "last", "size", "symbol"])
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

    # Partition by date first so each trading day is easy to inspect on disk.
    with_date.write_parquet(
        dataset_path,
        partition_by=["date", "symbol"],
    )

    return dataset_path
