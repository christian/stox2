from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from .config import get_paths


@dataclass(frozen=True)
class BarDatasetInfo:
    symbols: list[str]
    min_date: date | None
    max_date: date | None
    row_count: int
    disk_bytes: int


def bars_glob(*, source: str = "ib") -> str:
    paths = get_paths()
    return str(paths.raw / "bars" / f"source={source}" / "**" / "*.parquet")


def bars_scan(*, source: str = "ib") -> str:
    return f"read_parquet('{bars_glob(source=source)}', union_by_name=True)"


def _bars_exists(path_glob: str) -> bool:
    return any(Path(path_glob.rsplit("/**/*.parquet", 1)[0]).rglob("*.parquet"))


def _bars_disk_bytes(path_glob: str) -> int:
    root = Path(path_glob.rsplit("/**/*.parquet", 1)[0])
    return sum(path.stat().st_size for path in root.rglob("*.parquet"))


def describe_bars(*, source: str = "ib") -> BarDatasetInfo:
    path_glob = bars_glob(source=source)
    if not _bars_exists(path_glob):
        return BarDatasetInfo(
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
        FROM {bars_scan(source=source)}
    """
    symbols, min_date, max_date, row_count = duckdb.sql(query).fetchone()
    return BarDatasetInfo(
        symbols=list(symbols or []),
        min_date=min_date,
        max_date=max_date,
        row_count=row_count or 0,
        disk_bytes=_bars_disk_bytes(path_glob),
    )


def load_bar_summary(
    *,
    source: str = "ib",
    symbol: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    path_glob = bars_glob(source=source)
    if not _bars_exists(path_glob):
        return pd.DataFrame(
            columns=[
                "symbol",
                "date",
                "bars",
                "first_ts",
                "last_ts",
                "open_price",
                "high_price",
                "low_price",
                "close_price",
                "volume",
                "day_return_pct",
                "prev_close_pct",
            ]
        )

    where_clause = _where_clause(symbol=symbol, start_date=start_date, end_date=end_date)
    query = f"""
        WITH daily AS (
            SELECT
                symbol,
                date,
                COUNT(*) AS bars,
                MIN(ts) AS first_ts,
                MAX(ts) AS last_ts,
                arg_min(open, ts) AS open_price,
                MAX(high) AS high_price,
                MIN(low) AS low_price,
                arg_max(close, ts) AS close_price,
                SUM(volume) AS volume
            FROM {bars_scan(source=source)}
            {where_clause}
            GROUP BY symbol, date
        )
        SELECT
            symbol,
            date,
            bars,
            first_ts,
            last_ts,
            open_price,
            high_price,
            low_price,
            close_price,
            volume,
            (close_price / open_price - 1) * 100 AS day_return_pct,
            (close_price / LAG(close_price) OVER (PARTITION BY symbol ORDER BY date) - 1) * 100
                AS prev_close_pct
        FROM daily
        ORDER BY date DESC, symbol
    """
    return duckdb.sql(query).df()


def load_bars(
    *,
    source: str = "ib",
    symbol: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 5000,
) -> pd.DataFrame:
    path_glob = bars_glob(source=source)
    if not _bars_exists(path_glob):
        return pd.DataFrame(
            columns=["ts", "symbol", "open", "high", "low", "close", "volume", "date"]
        )

    where_clause = _where_clause(symbol=symbol, start_date=start_date, end_date=end_date)
    query = f"""
        SELECT ts, open, high, low, close, volume, symbol, date
        FROM {bars_scan(source=source)}
        {where_clause}
        ORDER BY ts DESC
        LIMIT {int(limit)}
    """
    return duckdb.sql(query).df()


def load_bar_symbol_counts(*, source: str = "ib") -> pd.DataFrame:
    path_glob = bars_glob(source=source)
    if not _bars_exists(path_glob):
        return pd.DataFrame(columns=["symbol", "bars"])

    query = f"""
        SELECT
            symbol,
            COUNT(*) AS bars
        FROM {bars_scan(source=source)}
        GROUP BY symbol
        ORDER BY bars DESC, symbol
    """
    return duckdb.sql(query).df()


def load_bar_chart_series(
    *,
    source: str = "ib",
    symbol: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    bucket: str = "day",
) -> pd.DataFrame:
    path_glob = bars_glob(source=source)
    if not _bars_exists(path_glob):
        return pd.DataFrame(
            columns=["bucket_ts", "session_date", "open", "high", "low", "close", "volume"]
        )

    bucket_exprs = {
        "1min": "date_trunc('minute', ts)",
        "5min": "to_timestamp(floor(epoch(ts) / 300) * 300)",
        "day": "CAST(date AS TIMESTAMP)",
    }
    if bucket not in bucket_exprs:
        raise ValueError(f"unsupported bucket: {bucket}")

    where_clause = _where_clause(symbol=symbol, start_date=start_date, end_date=end_date)
    query = f"""
        SELECT
            {bucket_exprs[bucket]} AS bucket_ts,
            date AS session_date,
            arg_min(open, ts) AS open,
            MAX(high) AS high,
            MIN(low) AS low,
            arg_max(close, ts) AS close,
            SUM(volume) AS volume
        FROM {bars_scan(source=source)}
        {where_clause}
        GROUP BY bucket_ts, session_date
        ORDER BY session_date, bucket_ts
    """
    return duckdb.sql(query).df()


def load_intraday_research(
    *,
    source: str = "ib",
    symbol: str | None = None,
    benchmark_symbol: str | None = "QQQ",
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    path_glob = bars_glob(source=source)
    columns = [
        "symbol",
        "date",
        "bars",
        "first_ts",
        "last_ts",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
        "vwap",
        "benchmark_symbol",
        "benchmark_premarket_return_pct",
        "benchmark_premarket_range_pct",
        "benchmark_premarket_up_pct",
        "benchmark_premarket_down_pct",
        "benchmark_premarket_direction",
        "first_30m_price_direction",
        "benchmark_premarket_agrees_with_first_30m",
        "realized_vol_1m_pct",
        "realized_vol_30m_pct",
        "rest_of_day_realized_vol_pct",
        "first_30m_volume_pct",
        "time_of_high",
        "time_of_low",
        "max_intraday_drawdown_pct",
        "day_return_pct",
        "first_5m_return_pct",
        "first_15m_return_pct",
        "first_30m_return_pct",
        "opening_range_30m_pct",
        "opening_range_broken_up",
        "opening_range_broken_down",
        "rest_of_day_return_pct",
        "close_vs_vwap_pct",
        "max_favorable_from_open_pct",
        "max_adverse_from_open_pct",
        "biggest_1m_up_pct",
        "biggest_1m_down_pct",
        "biggest_5m_up_pct",
        "biggest_5m_down_pct",
    ]
    if not _bars_exists(path_glob):
        return pd.DataFrame(columns=columns)

    where_clause = _where_clause(symbol=symbol, start_date=start_date, end_date=end_date)
    benchmark_symbol_sql = (benchmark_symbol or "").upper().replace("'", "''")
    query = f"""
        WITH filtered AS (
            SELECT *
            FROM {bars_scan(source=source)}
            {where_clause}
        ),
        annotated AS (
            SELECT
                *,
                MIN(ts) OVER (PARTITION BY symbol, date) AS session_start,
                FIRST_VALUE(open) OVER (
                    PARTITION BY symbol, date
                    ORDER BY ts
                    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                ) AS session_open,
                (close / LAG(close) OVER (PARTITION BY symbol, date ORDER BY ts) - 1) * 100
                    AS ret_1m_pct,
                (close / LAG(close, 5) OVER (PARTITION BY symbol, date ORDER BY ts) - 1) * 100
                    AS ret_5m_pct,
                MAX(high) OVER (
                    PARTITION BY symbol, date
                    ORDER BY ts
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS running_high
            FROM filtered
        ),
        metrics AS (
            SELECT
                symbol,
                date,
                COUNT(*) AS bars,
                MIN(ts) AS first_ts,
                MAX(ts) AS last_ts,
                arg_min(open, ts) AS open_price,
                MAX(high) AS high_price,
                MIN(low) AS low_price,
                arg_max(ts, high) AS time_of_high,
                arg_min(ts, low) AS time_of_low,
                arg_max(close, ts) AS close_price,
                SUM(volume) AS volume,
                SUM(close * volume) / NULLIF(SUM(volume), 0) AS vwap,
                SQRT(SUM(POWER(ret_1m_pct, 2))) AS realized_vol_1m_pct,
                SQRT(SUM(POWER(ret_1m_pct, 2)) FILTER (
                    WHERE ts < session_start + INTERVAL 30 MINUTE
                )) AS realized_vol_30m_pct,
                SQRT(SUM(POWER(ret_1m_pct, 2)) FILTER (
                    WHERE ts >= session_start + INTERVAL 30 MINUTE
                )) AS rest_of_day_realized_vol_pct,
                SUM(volume) FILTER (
                    WHERE ts < session_start + INTERVAL 30 MINUTE
                ) / NULLIF(SUM(volume), 0) * 100 AS first_30m_volume_pct,
                arg_max(close, ts) FILTER (
                    WHERE ts < session_start + INTERVAL 5 MINUTE
                ) AS close_5m,
                arg_max(close, ts) FILTER (
                    WHERE ts < session_start + INTERVAL 15 MINUTE
                ) AS close_15m,
                arg_max(close, ts) FILTER (
                    WHERE ts < session_start + INTERVAL 30 MINUTE
                ) AS close_30m,
                MAX(high) FILTER (
                    WHERE ts < session_start + INTERVAL 30 MINUTE
                ) AS high_30m,
                MIN(low) FILTER (
                    WHERE ts < session_start + INTERVAL 30 MINUTE
                ) AS low_30m,
                MAX(high) FILTER (
                    WHERE ts >= session_start + INTERVAL 30 MINUTE
                ) AS high_after_30m,
                MIN(low) FILTER (
                    WHERE ts >= session_start + INTERVAL 30 MINUTE
                ) AS low_after_30m,
                MAX((high / session_open - 1) * 100) AS max_favorable_from_open_pct,
                MIN((low / session_open - 1) * 100) AS max_adverse_from_open_pct,
                MIN((low / running_high - 1) * 100) AS max_intraday_drawdown_pct,
                MAX(ret_1m_pct) AS biggest_1m_up_pct,
                MIN(ret_1m_pct) AS biggest_1m_down_pct,
                MAX(ret_5m_pct) AS biggest_5m_up_pct,
                MIN(ret_5m_pct) AS biggest_5m_down_pct
            FROM annotated
            GROUP BY symbol, date
        ),
        benchmark_premarket AS (
            SELECT
                m.symbol,
                m.date,
                '{benchmark_symbol_sql}' AS benchmark_symbol,
                arg_min(b.open, b.ts) AS benchmark_premarket_open,
                arg_max(b.close, b.ts) AS benchmark_premarket_close,
                MAX(b.high) AS benchmark_premarket_high,
                MIN(b.low) AS benchmark_premarket_low
            FROM metrics m
            LEFT JOIN {bars_scan(source=source)} b
                ON b.symbol = '{benchmark_symbol_sql}'
                AND b.date = m.date
                AND b.ts < m.first_ts
            GROUP BY m.symbol, m.date
        ),
        final_metrics AS (
            SELECT
                m.*,
                b.benchmark_symbol,
                (
                    b.benchmark_premarket_close / b.benchmark_premarket_open - 1
                ) * 100 AS benchmark_premarket_return_pct,
                (
                    b.benchmark_premarket_high - b.benchmark_premarket_low
                ) / b.benchmark_premarket_open * 100 AS benchmark_premarket_range_pct,
                (
                    b.benchmark_premarket_high / b.benchmark_premarket_open - 1
                ) * 100 AS benchmark_premarket_up_pct,
                (
                    b.benchmark_premarket_low / b.benchmark_premarket_open - 1
                ) * 100 AS benchmark_premarket_down_pct
            FROM metrics m
            LEFT JOIN benchmark_premarket b
                ON b.symbol = m.symbol
                AND b.date = m.date
        )
        SELECT
            symbol,
            date,
            bars,
            first_ts,
            last_ts,
            open_price,
            high_price,
            low_price,
            close_price,
            volume,
            vwap,
            benchmark_symbol,
            benchmark_premarket_return_pct,
            benchmark_premarket_range_pct,
            benchmark_premarket_up_pct,
            benchmark_premarket_down_pct,
            CASE
                WHEN benchmark_premarket_return_pct > 0 THEN 'UP'
                WHEN benchmark_premarket_return_pct < 0 THEN 'DOWN'
                WHEN benchmark_premarket_return_pct = 0 THEN 'FLAT'
                ELSE NULL
            END AS benchmark_premarket_direction,
            CASE
                WHEN (close_30m / open_price - 1) > 0 THEN 'UP'
                WHEN (close_30m / open_price - 1) < 0 THEN 'DOWN'
                WHEN (close_30m / open_price - 1) = 0 THEN 'FLAT'
                ELSE NULL
            END AS first_30m_price_direction,
            CASE
                WHEN benchmark_premarket_return_pct IS NULL OR close_30m IS NULL THEN NULL
                WHEN benchmark_premarket_return_pct = 0 OR (close_30m / open_price - 1) = 0 THEN NULL
                ELSE (benchmark_premarket_return_pct > 0) = ((close_30m / open_price - 1) > 0)
            END AS benchmark_premarket_agrees_with_first_30m,
            realized_vol_1m_pct,
            realized_vol_30m_pct,
            rest_of_day_realized_vol_pct,
            first_30m_volume_pct,
            time_of_high,
            time_of_low,
            max_intraday_drawdown_pct,
            (close_price / open_price - 1) * 100 AS day_return_pct,
            (close_5m / open_price - 1) * 100 AS first_5m_return_pct,
            (close_15m / open_price - 1) * 100 AS first_15m_return_pct,
            (close_30m / open_price - 1) * 100 AS first_30m_return_pct,
            (high_30m - low_30m) / open_price * 100 AS opening_range_30m_pct,
            COALESCE(high_after_30m > high_30m, FALSE) AS opening_range_broken_up,
            COALESCE(low_after_30m < low_30m, FALSE) AS opening_range_broken_down,
            (close_price / close_30m - 1) * 100 AS rest_of_day_return_pct,
            (close_price / vwap - 1) * 100 AS close_vs_vwap_pct,
            max_favorable_from_open_pct,
            max_adverse_from_open_pct,
            biggest_1m_up_pct,
            biggest_1m_down_pct,
            biggest_5m_up_pct,
            biggest_5m_down_pct
        FROM final_metrics
        ORDER BY date DESC, symbol
    """
    return duckdb.sql(query).df()[columns]


def load_intraday_indicator_series(
    *,
    source: str = "ib",
    symbol: str,
    session_date: date,
) -> pd.DataFrame:
    path_glob = bars_glob(source=source)
    columns = [
        "ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "session_open",
        "vwap",
        "opening_range_high_30m",
        "opening_range_low_30m",
    ]
    if not _bars_exists(path_glob):
        return pd.DataFrame(columns=columns)

    symbol_sql = symbol.upper().replace("'", "''")
    query = f"""
        WITH day_bars AS (
            SELECT *
            FROM {bars_scan(source=source)}
            WHERE symbol = '{symbol_sql}'
                AND date = DATE '{session_date.isoformat()}'
        ),
        annotated AS (
            SELECT
                *,
                MIN(ts) OVER () AS session_start,
                FIRST_VALUE(open) OVER (
                    ORDER BY ts
                    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                ) AS session_open,
                SUM(close * volume) OVER (
                    ORDER BY ts
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) / NULLIF(
                    SUM(volume) OVER (
                        ORDER BY ts
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ),
                    0
                ) AS vwap
            FROM day_bars
        ),
        levels AS (
            SELECT
                MAX(high) FILTER (
                    WHERE ts < session_start + INTERVAL 30 MINUTE
                ) AS opening_range_high_30m,
                MIN(low) FILTER (
                    WHERE ts < session_start + INTERVAL 30 MINUTE
                ) AS opening_range_low_30m
            FROM annotated
        )
        SELECT
            ts,
            open,
            high,
            low,
            close,
            volume,
            session_open,
            vwap,
            opening_range_high_30m,
            opening_range_low_30m
        FROM annotated
        CROSS JOIN levels
        ORDER BY ts
    """
    return duckdb.sql(query).df()[columns]


def _where_clause(
    *,
    symbol: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> str:
    filters: list[str] = []
    if symbol:
        filters.append(f"symbol = '{symbol.upper()}'")
    if start_date:
        filters.append(f"date >= DATE '{start_date.isoformat()}'")
    if end_date:
        filters.append(f"date <= DATE '{end_date.isoformat()}'")
    return f"WHERE {' AND '.join(filters)}" if filters else ""
