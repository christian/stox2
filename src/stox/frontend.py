from __future__ import annotations

from datetime import timedelta

import altair as alt
import pandas as pd
import streamlit as st

from .explore import (
    describe_bars,
    load_bar_chart_series,
    load_bar_summary,
    load_bar_symbol_counts,
    load_bars,
    load_intraday_indicator_series,
    load_intraday_research,
)


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
    st.caption("Dataset-level storage and coverage details for local parquet bars.")

    left, middle, right = st.columns(3)
    left.metric("Bars", f"{info.row_count:,}")
    middle.metric("Symbols", len(info.symbols))
    right.metric("Parquet Size", _format_bytes(info.disk_bytes))

    st.subheader("Coverage")
    st.write(f"Date range: `{info.min_date}` to `{info.max_date}`")

    st.subheader("Symbols")
    symbol_counts = load_bar_symbol_counts()
    st.dataframe(
        symbol_counts,
        width="stretch",
        hide_index=True,
    )


def _chart_bucket(days: int) -> tuple[str, str]:
    if days <= 5:
        return "1min", "Close Price Per Minute"
    return "day", "Daily Close Price"


def _with_session_breaks(chart_data: pd.DataFrame) -> pd.DataFrame:
    if chart_data.empty or "session_date" not in chart_data.columns:
        return chart_data

    frames: list[pd.DataFrame] = []
    for _, group in chart_data.groupby("session_date", sort=True):
        frames.append(group)
        frames.append(
            pd.DataFrame(
                [
                    {
                        "bucket_ts": pd.NaT,
                        "session_date": None,
                        "open": None,
                        "high": None,
                        "low": None,
                        "close": None,
                        "volume": None,
                    }
                ]
            )
        )
    return pd.concat(frames, ignore_index=True)


def _price_domain(chart_data: pd.DataFrame) -> list[float] | None:
    prices = chart_data["close"].dropna()
    if prices.empty:
        return None

    low = float(prices.min())
    high = float(prices.max())
    if low == high:
        pad = max(abs(low) * 0.01, 0.01)
    else:
        pad = (high - low) * 0.05
    return [low - pad, high + pad]


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
        summary.style.format(
            {
                "open_price": "{:.2f}",
                "high_price": "{:.2f}",
                "low_price": "{:.2f}",
                "close_price": "{:.2f}",
                "volume": "{:,.0f}",
                "day_return_pct": lambda value: "" if pd.isna(value) else f"{value:+.2f}%",
                "prev_close_pct": lambda value: "" if pd.isna(value) else f"{value:+.2f}%",
            }
        )
        .map(_pct_color, subset=["day_return_pct", "prev_close_pct"])
    )


def _style_research(research: pd.DataFrame):
    def _pct_color(value):
        if pd.isna(value):
            return ""
        if value > 0:
            return "color: #17803d; font-weight: 600;"
        if value < 0:
            return "color: #c62828; font-weight: 600;"
        return ""

    pct_cols = [
        "day_return_pct",
        "benchmark_premarket_return_pct",
        "benchmark_premarket_range_pct",
        "benchmark_premarket_up_pct",
        "benchmark_premarket_down_pct",
        "realized_vol_1m_pct",
        "realized_vol_30m_pct",
        "rest_of_day_realized_vol_pct",
        "first_30m_volume_pct",
        "max_intraday_drawdown_pct",
        "first_5m_return_pct",
        "first_15m_return_pct",
        "first_30m_return_pct",
        "opening_range_30m_pct",
        "rest_of_day_return_pct",
        "close_vs_vwap_pct",
        "max_favorable_from_open_pct",
        "max_adverse_from_open_pct",
        "biggest_1m_up_pct",
        "biggest_1m_down_pct",
        "biggest_5m_up_pct",
        "biggest_5m_down_pct",
    ]
    return (
        research.style.format(
            {
                "open_price": "{:.2f}",
                "high_price": "{:.2f}",
                "low_price": "{:.2f}",
                "close_price": "{:.2f}",
                "volume": "{:,.0f}",
                "vwap": "{:.2f}",
                **{
                    col: (lambda value: "" if pd.isna(value) else f"{value:+.2f}%")
                    for col in pct_cols
                },
            }
        )
        .map(_pct_color, subset=pct_cols)
    )


def _render_day_indicator_chart(symbol: str, research: pd.DataFrame) -> None:
    if research.empty:
        return

    available_dates = research["date"].sort_values(ascending=False).tolist()
    selected_date = st.selectbox(
        "Day",
        available_dates,
        format_func=lambda value: value.isoformat(),
        key="indicator_day",
    )
    day_data = load_intraday_indicator_series(symbol=symbol, session_date=selected_date)
    if day_data.empty:
        st.info("No bars found for the selected day.")
        return

    chart_data = day_data.copy()
    chart_data["ts"] = pd.to_datetime(chart_data["ts"])
    line_data = chart_data.melt(
        id_vars=["ts"],
        value_vars=["close", "vwap", "session_open", "opening_range_high_30m", "opening_range_low_30m"],
        var_name="indicator",
        value_name="price",
    )
    label_map = {
        "close": "Close",
        "vwap": "VWAP",
        "session_open": "Open",
        "opening_range_high_30m": "30m High",
        "opening_range_low_30m": "30m Low",
    }
    line_data["indicator"] = line_data["indicator"].map(label_map)

    domain = _price_domain(chart_data)
    price_chart = (
        alt.Chart(line_data)
        .mark_line()
        .encode(
            x=alt.X("ts:T", title="Time"),
            y=alt.Y("price:Q", title="Price", scale=alt.Scale(domain=domain, zero=False)),
            color=alt.Color(
                "indicator:N",
                title="Indicator",
                scale=alt.Scale(
                    domain=["Close", "VWAP", "Open", "30m High", "30m Low"],
                    range=["#1f77b4", "#f59e0b", "#6b7280", "#15803d", "#b91c1c"],
                ),
            ),
            strokeDash=alt.StrokeDash(
                "indicator:N",
                legend=None,
                scale=alt.Scale(
                    domain=["Close", "VWAP", "Open", "30m High", "30m Low"],
                    range=[[1, 0], [1, 0], [5, 4], [6, 3], [6, 3]],
                ),
            ),
            tooltip=[
                alt.Tooltip("ts:T", title="Time"),
                alt.Tooltip("indicator:N", title="Indicator"),
                alt.Tooltip("price:Q", title="Price", format=".2f"),
            ],
        )
        .properties(height=360)
    )
    st.altair_chart(price_chart, width="stretch")

    volume_chart = (
        alt.Chart(chart_data)
        .mark_bar(color="#9ca3af")
        .encode(
            x=alt.X("ts:T", title="Time"),
            y=alt.Y("volume:Q", title="Volume"),
            tooltip=[
                alt.Tooltip("ts:T", title="Time"),
                alt.Tooltip("volume:Q", title="Volume", format=",.0f"),
            ],
        )
        .properties(height=160)
    )
    st.altair_chart(volume_chart, width="stretch")


def render_empty_state() -> bool:
    info = describe_bars()
    if info.row_count == 0:
        st.title("stox2 Bars Explorer")
        st.warning("No bar parquet files found under data/raw/bars/source=ib.")
        st.code(
            "uv run python -m stox.ingest.ib_fetch_bars --symbol CRWV "
            "--past-year "
            '--bar-size "1 min" --what TRADES --use-rth --port 4001'
        )
        return True
    return False


def render_settings_page() -> None:
    if render_empty_state():
        return
    _render_settings(describe_bars())


def render_explorer_page() -> None:
    if render_empty_state():
        return

    info = describe_bars()

    selected_symbol = st.pills(
        "Symbol",
        info.symbols,
        selection_mode="single",
        default=info.symbols[0],
    )
    if selected_symbol is None:
        selected_symbol = info.symbols[0]

    st.title(selected_symbol)
    st.caption("Browse locally stored IB parquet OHLCV bars by date range.")

    min_date = info.min_date
    max_date = info.max_date
    range_preset = st.session_state.get("range_preset", "Last 5 days")
    days = {"Last day": 1, "Last 5 days": 5, "Last 30 days": 30}[range_preset]
    row_limit = st.session_state.get("row_limit", 2000)
    benchmark_symbol = st.session_state.get("benchmark_symbol", "QQQ")

    end_date = max_date
    start_date = max(min_date, _range_start(max_date, days)) if min_date and max_date else None

    summary = load_bar_summary(symbol=selected_symbol, start_date=start_date, end_date=end_date)
    research = load_intraday_research(
        symbol=selected_symbol,
        benchmark_symbol=benchmark_symbol,
    )
    bars = load_bars(symbol=selected_symbol, start_date=start_date, end_date=end_date, limit=row_limit)
    bucket, chart_title = _chart_bucket(days)
    chart_series = load_bar_chart_series(
        symbol=selected_symbol,
        start_date=start_date,
        end_date=end_date,
        bucket=bucket,
    )

    st.subheader("Daily OHLCV")
    st.dataframe(_style_summary(summary), width="stretch", hide_index=True)

    st.subheader("Intraday Research")
    st.caption("All available days for the selected symbol.")
    st.dataframe(_style_research(research), width="stretch", hide_index=True)
    st.text_input(
        "Nasdaq proxy symbol",
        value=benchmark_symbol,
        key="benchmark_symbol",
    )

    st.subheader("Single-Day Indicators")
    _render_day_indicator_chart(selected_symbol, research)

    if not chart_series.empty:
        chart_data = chart_series.copy()
        chart_data["bucket_ts"] = pd.to_datetime(chart_data["bucket_ts"])
        if bucket != "day":
            chart_data = _with_session_breaks(chart_data)

        st.subheader(chart_title)
        domain = _price_domain(chart_data)
        close_chart = (
            alt.Chart(chart_data)
            .mark_line()
            .encode(
                x=alt.X("bucket_ts:T", title="Time"),
                y=alt.Y("close:Q", title="Close", scale=alt.Scale(domain=domain, zero=False)),
                tooltip=[
                    alt.Tooltip("bucket_ts:T", title="Time"),
                    alt.Tooltip("open:Q", title="Open", format=".2f"),
                    alt.Tooltip("high:Q", title="High", format=".2f"),
                    alt.Tooltip("low:Q", title="Low", format=".2f"),
                    alt.Tooltip("close:Q", title="Close", format=".2f"),
                    alt.Tooltip("volume:Q", title="Volume", format=",.0f"),
                ],
            )
            .properties(height=320)
        )
        st.altair_chart(close_chart, width="stretch")

        st.subheader("Volume")
        volume_chart = (
            alt.Chart(chart_data)
            .mark_bar()
            .encode(
                x=alt.X("bucket_ts:T", title="Time"),
                y=alt.Y("volume:Q", title="Volume"),
            )
            .properties(height=220)
        )
        st.altair_chart(volume_chart, width="stretch")

    st.pills(
        "Range",
        ["Last day", "Last 5 days", "Last 30 days"],
        selection_mode="single",
        default=range_preset,
        key="range_preset",
    )

    st.subheader("Raw Bars")
    st.dataframe(bars, width="stretch", hide_index=True)

    st.slider(
        "Raw bar rows",
        min_value=100,
        max_value=10000,
        value=row_limit,
        step=100,
        key="row_limit",
    )


if __name__ == "__main__":
    render_explorer_page()
