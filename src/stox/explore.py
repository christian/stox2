from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from .config import get_paths


@dataclass(frozen=True)
class TickDatasetInfo:
    symbols: list[str]
    min_date: date | None
    max_date: date | None
    row_count: int
    disk_bytes: int


def ticks_glob(*, source: str = "ib") -> str:
    paths = get_paths()
    return str(paths.raw / "ticks" / f"source={source}" / "**" / "*.parquet")


def ticks_scan(*, source: str = "ib") -> str:
    return f"read_parquet('{ticks_glob(source=source)}', union_by_name=True)"


def _ticks_exists(path_glob: str) -> bool:
    return any(Path(path_glob.rsplit("/**/*.parquet", 1)[0]).rglob("*.parquet"))


def _ticks_disk_bytes(path_glob: str) -> int:
    root = Path(path_glob.rsplit("/**/*.parquet", 1)[0])
    return sum(path.stat().st_size for path in root.rglob("*.parquet"))


def describe_ticks(*, source: str = "ib") -> TickDatasetInfo:
    path_glob = ticks_glob(source=source)
    if not _ticks_exists(path_glob):
        return TickDatasetInfo(
            symbols=[],
            min_date=None,
            max_date=None,
            row_count=0,
            disk_bytes=0,
        )

    query = f"""
        SELECT
            list_sort(list(DISTINCT symbol)) AS symbols,
            MIN(date) AS min_date,
            MAX(date) AS max_date,
            COUNT(*) AS row_count
        FROM {ticks_scan(source=source)}
    """
    row = duckdb.sql(query).fetchone()
    symbols, min_date, max_date, row_count = row
    return TickDatasetInfo(
        symbols=list(symbols or []),
        min_date=min_date,
        max_date=max_date,
        row_count=row_count or 0,
        disk_bytes=_ticks_disk_bytes(path_glob),
    )


def load_tick_summary(
    *,
    source: str = "ib",
    symbol: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    path_glob = ticks_glob(source=source)
    if not _ticks_exists(path_glob):
        return pd.DataFrame(
            columns=[
                "symbol",
                "date",
                "rows",
                "first_ts",
                "last_ts",
                "close_price",
                "prev_close_pct",
            ]
        )

    filters: list[str] = []
    if symbol:
        filters.append(f"symbol = '{symbol.upper()}'")
    if start_date:
        filters.append(f"date >= DATE '{start_date.isoformat()}'")
    if end_date:
        filters.append(f"date <= DATE '{end_date.isoformat()}'")

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = f"""
        WITH daily AS (
            SELECT
                symbol,
                date,
                COUNT(*) AS rows,
                MIN(ts) AS first_ts,
                MAX(ts) AS last_ts,
                arg_max(last, ts) AS close_price
            FROM {ticks_scan(source=source)}
            {where_clause}
            GROUP BY symbol, date
        )
        SELECT
            symbol,
            date,
            rows,
            first_ts,
            last_ts,
            close_price,
            (close_price / LAG(close_price) OVER (PARTITION BY symbol ORDER BY date) - 1) * 100
                AS prev_close_pct
        FROM daily
        ORDER BY date DESC, symbol
    """
    return duckdb.sql(query).df()


def load_ticks(
    *,
    source: str = "ib",
    symbol: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 5000,
) -> pd.DataFrame:
    path_glob = ticks_glob(source=source)
    if not _ticks_exists(path_glob):
        return pd.DataFrame(columns=["ts", "symbol", "last", "size", "date"])

    filters: list[str] = []
    if symbol:
        filters.append(f"symbol = '{symbol.upper()}'")
    if start_date:
        filters.append(f"date >= DATE '{start_date.isoformat()}'")
    if end_date:
        filters.append(f"date <= DATE '{end_date.isoformat()}'")

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = f"""
        SELECT ts, last, size, symbol, date
        FROM {ticks_scan(source=source)}
        {where_clause}
        ORDER BY ts DESC
        LIMIT {int(limit)}
    """
    return duckdb.sql(query).df()


def load_symbol_counts(*, source: str = "ib") -> pd.DataFrame:
    path_glob = ticks_glob(source=source)
    if not _ticks_exists(path_glob):
        return pd.DataFrame(columns=["symbol", "rows"])

    query = f"""
        SELECT
            symbol,
            COUNT(*) AS rows
        FROM {ticks_scan(source=source)}
        GROUP BY symbol
        ORDER BY rows DESC, symbol
    """
    return duckdb.sql(query).df()


def load_chart_series(
    *,
    source: str = "ib",
    symbol: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    bucket: str = "day",
) -> pd.DataFrame:
    path_glob = ticks_glob(source=source)
    if not _ticks_exists(path_glob):
        return pd.DataFrame(columns=["bucket_ts", "session_date", "close_price", "volume"])

    bucket_exprs = {
        "1min": "date_trunc('minute', ts)",
        "5min": "to_timestamp(floor(epoch(ts) / 300) * 300)",
        "day": "CAST(date AS TIMESTAMP)",
    }
    if bucket not in bucket_exprs:
        raise ValueError(f"unsupported bucket: {bucket}")

    filters: list[str] = []
    if symbol:
        filters.append(f"symbol = '{symbol.upper()}'")
    if start_date:
        filters.append(f"date >= DATE '{start_date.isoformat()}'")
    if end_date:
        filters.append(f"date <= DATE '{end_date.isoformat()}'")

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = f"""
        SELECT
            {bucket_exprs[bucket]} AS bucket_ts,
            date AS session_date,
            arg_max(last, ts) AS close_price,
            SUM(size) AS volume
        FROM {ticks_scan(source=source)}
        {where_clause}
        GROUP BY bucket_ts, session_date
        ORDER BY session_date, bucket_ts
    """
    return duckdb.sql(query).df()
