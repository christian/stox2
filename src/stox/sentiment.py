from __future__ import annotations

from pathlib import Path
import polars as pl

from .config import get_paths


def normalize_sentiment(df: pl.DataFrame) -> pl.DataFrame:
    required = {"ts", "symbol", "sentiment"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")

    out = df.with_columns(
        [
            pl.col("ts").cast(pl.Datetime),
            pl.col("symbol").str.to_uppercase(),
            pl.col("sentiment").cast(pl.Float64),
        ]
    )
    return out


def write_sentiment(
    df: pl.DataFrame,
    *,
    source: str,
    dataset: str = "sentiment",
) -> Path:
    paths = get_paths()
    dataset_path = paths.raw / dataset / f"source={source}"
    dataset_path.mkdir(parents=True, exist_ok=True)

    normalized = normalize_sentiment(df)
    with_date = normalized.with_columns(pl.col("ts").dt.date().alias("date"))

    with_date.write_parquet(
        dataset_path,
        partition_by=["symbol", "date"],
    )

    return dataset_path


def load_sentiment_csv(
    path: Path,
    *,
    ts_col: str = "ts",
    symbol_col: str = "symbol",
    score_col: str = "sentiment",
    tz: str | None = "UTC",
) -> pl.DataFrame:
    df = pl.read_csv(path)
    df = df.rename({ts_col: "ts", symbol_col: "symbol", score_col: "sentiment"})

    df = df.with_columns(pl.col("ts").str.strptime(pl.Datetime, strict=False))
    if tz:
        df = df.with_columns(pl.col("ts").dt.replace_time_zone(tz))

    return normalize_sentiment(df)
