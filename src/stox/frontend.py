from __future__ import annotations

from datetime import timedelta

import altair as alt
import pandas as pd
import streamlit as st

from .explore import describe_ticks, load_chart_series, load_symbol_counts, load_tick_summary, load_ticks


def _range_start(max_date, days: int):
    if max_date is None:
        return None
    return max_date - timedelta(days=days - 1)


def _format_bytes(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024


def _render_settings(info) -> None:
    st.title("Settings")
    st.caption("Dataset-level storage and coverage details for local parquet ticks.")

    left, middle, right = st.columns(3)
    left.metric("Rows", f"{info.row_count:,}")
    middle.metric("Symbols", len(info.symbols))
    right.metric("Parquet Size", _format_bytes(info.disk_bytes))

    st.subheader("Coverage")
    st.write(f"Date range: `{info.min_date}` to `{info.max_date}`")

    st.subheader("Symbols")
    symbol_counts = load_symbol_counts()
    st.dataframe(
        symbol_counts,
        use_container_width=True,
        hide_index=True,
    )


def _chart_bucket(days: int) -> tuple[str, str]:
    if days <= 1:
        return "1min", "Close Price Per Minute"
    if days <= 5:
        return "5min", "Close Price Per 5 Minutes"
    return "day", "Close Price Per Day"


def _with_session_breaks(chart_data: pd.DataFrame) -> pd.DataFrame:
    if chart_data.empty or "session_date" not in chart_data.columns:
        return chart_data

    frames: list[pd.DataFrame] = []
    for _, group in chart_data.groupby("session_date", sort=True):
        frames.append(group)
        frames.append(
            pd.DataFrame(
                [{"bucket_ts": pd.NaT, "session_date": None, "close_price": None, "volume": None}]
            )
        )
    return pd.concat(frames, ignore_index=True)


def _price_domain(chart_data: pd.DataFrame) -> list[float] | None:
    prices = chart_data["close_price"].dropna()
    if prices.empty:
        return None

    low = float(prices.min())
    high = float(prices.max())
    if low == high:
        pad = max(abs(low) * 0.01, 0.01)
    else:
        pad = (high - low) * 0.05
    return [low - pad, high + pad]


def _format_summary(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return summary

    out = summary.copy()
    return out


def _style_summary(summary: pd.DataFrame):
    def _pct_color(value):
        if pd.isna(value):
            return ""
        if value > 0:
            return "color: #17803d; font-weight: 600;"
        if value < 0:
            return "color: #c62828; font-weight: 600;"
        return ""

    return (
        _format_summary(summary)
        .style.format(
            {
                "close_price": "{:.2f}",
                "prev_close_pct": lambda value: "" if pd.isna(value) else f"{value:+.2f}%",
            }
        )
        .map(_pct_color, subset=["prev_close_pct"])
    )


def render_empty_state() -> None:
    info = describe_ticks()
    if info.row_count == 0:
        st.title("stox2 Tick Explorer")
        st.warning("No tick parquet files found under data/raw/ticks/source=ib.")
        st.code(
            "uv run python -m stox.ingest.ib_fetch --symbol AAPL --start 2025-02-01T14:30:00Z "
            "--end 2025-02-01T20:00:00Z --port 4001"
        )
        return True
    return False


def render_settings_page() -> None:
    if render_empty_state():
        return
    _render_settings(describe_ticks())


def render_explorer_page() -> None:
    if render_empty_state():
        return

    info = describe_ticks()

    selected_symbol = st.pills(
        "Symbol",
        info.symbols,
        selection_mode="single",
        default=info.symbols[0],
    )
    if selected_symbol is None:
        selected_symbol = info.symbols[0]

    st.title(selected_symbol)
    st.caption("Browse locally stored IB parquet ticks by date range.")

    min_date = info.min_date
    max_date = info.max_date
    range_preset = st.session_state.get("range_preset", "Last 5 days")
    days = {"Last day": 1, "Last 5 days": 5, "Last 30 days": 30}[range_preset]
    row_limit = st.session_state.get("row_limit", 2000)

    end_date = max_date
    start_date = max(min_date, _range_start(max_date, days)) if min_date and max_date else None

    summary = load_tick_summary(symbol=selected_symbol, start_date=start_date, end_date=end_date)
    ticks = load_ticks(symbol=selected_symbol, start_date=start_date, end_date=end_date, limit=row_limit)
    bucket, chart_title = _chart_bucket(days)
    chart_series = load_chart_series(
        symbol=selected_symbol,
        start_date=start_date,
        end_date=end_date,
        bucket=bucket,
    )

    st.subheader("Daily Summary")
    st.dataframe(_style_summary(summary), use_container_width=True, hide_index=True)

    if not chart_series.empty:
        chart_data = chart_series.copy()
        chart_data["bucket_ts"] = pd.to_datetime(chart_data["bucket_ts"])
        if bucket != "day":
            chart_data = _with_session_breaks(chart_data)
        st.subheader(chart_title)
        domain = _price_domain(chart_data)
        chart = (
            alt.Chart(chart_data)
            .mark_line()
            .encode(
                x=alt.X("bucket_ts:T", title="Time"),
                y=alt.Y("close_price:Q", title="Price", scale=alt.Scale(domain=domain, zero=False)),
            )
            .properties(height=320)
        )
        st.altair_chart(chart, use_container_width=True)

        st.subheader("Aggregated Volume")
        volume_chart = (
            alt.Chart(chart_data)
            .mark_bar()
            .encode(
                x=alt.X("bucket_ts:T", title="Time"),
                y=alt.Y("volume:Q", title="Volume"),
            )
            .properties(height=220)
        )
        st.altair_chart(volume_chart, use_container_width=True)

    st.pills(
        "Range",
        ["Last day", "Last 5 days", "Last 30 days"],
        selection_mode="single",
        default=range_preset,
        key="range_preset",
    )

    st.subheader("Raw Ticks")
    st.dataframe(ticks, use_container_width=True, hide_index=True)

    st.slider(
        "Raw tick rows",
        min_value=100,
        max_value=10000,
        value=row_limit,
        step=100,
        key="row_limit",
    )


if __name__ == "__main__":
    render_explorer_page()
