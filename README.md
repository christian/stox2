# stox2

Offline bars store + ML sandbox for US stocks. The focus is:
- ingesting OHLCV bar data from IB
- storing partitioned Parquet locally
- feature/label pipelines for 30–60 min forward returns
- ML experiments in notebooks

## Quickstart

1) Create env and install deps:

```bash
uv venv
uv sync
```

2) Start TWS or IB Gateway.

3) Fetch full-session 1-minute OHLCV bars:

```bash
uv run python -m stox.ingest.ib_fetch_bars \
  --symbol CRWV \
  --exchange SMART \
  --currency USD \
  --past-year \
  --bar-size "1 min" \
  --what TRADES \
  --use-rth \
  --port 4001
```

Fetch `QQQ` extended-hours bars to populate Nasdaq proxy premarket columns:

```bash
uv run python -m stox.ingest.ib_fetch_bars \
  --symbol QQQ \
  --exchange SMART \
  --currency USD \
  --past-year \
  --bar-size "1 min" \
  --what TRADES \
  --port 4001
```

Fetch six months of 1-minute regular-hours bars for a basket:

```bash
uv run python -m stox.ingest.ib_fetch_bars_batch \
  --symbols AAOI,LITE,COHR,CIEN,NBIS,SNDK,RGTI,IONQ,IREN,APLD,WOLF \
  --past-months 6 \
  --bar-size "1 min" \
  --what TRADES \
  --use-rth \
  --port 4001
```

4) Query with DuckDB (example):

```python
import duckdb
con = duckdb.connect()
con.sql("""
  SELECT symbol, date, COUNT(*) AS n
  FROM read_parquet('data/raw/bars/source=ib/**/*.parquet')
  GROUP BY ALL
  ORDER BY date DESC
""").df()
```

5) Launch the local explorer:

```bash
uv run streamlit run streamlit_app.py
```

This opens a small local UI for browsing OHLCV bar parquet data by symbol and date range.
The app exposes `Explorer` and `Settings` in the sidebar.

Run an opening-range breakout backtest:

```bash
uv run python -m stox.backtest \
  --symbol CRWV \
  --strategy orb \
  --range-minutes 30 \
  --side long \
  --exit-after-minutes 60 \
  --transaction-cost-bps 1
```

Run a first-5-minute direction backtest:

```bash
uv run python -m stox.backtest \
  --symbol CRWV \
  --strategy first5 \
  --signal-minutes 5 \
  --exit-after-minutes 30 \
  --require-benchmark-alignment \
  --transaction-cost-bps 1
```

Run the premarket confirmation strategy across the high-volatility basket:

```bash
uv run python -m stox.backtest \
  --symbols AAOI,LITE,COHR,CIEN,NBIS,SNDK,RGTI,IONQ,IREN,APLD,WOLF \
  --strategy premarket5 \
  --premarket-threshold-pct 0.5 \
  --signal-minutes 5 \
  --exit-after-minutes 30 \
  --profit-target-pct 10 \
  --transaction-cost-bps 1
```

This strategy needs extended-hours bars because it uses each stock's own premarket move. Fetch
the strategy basket without `--use-rth` before running it:

```bash
uv run python -m stox.ingest.ib_fetch_bars_batch \
  --symbols AAOI,LITE,COHR,CIEN,NBIS,SNDK,RGTI,IONQ,IREN,APLD,WOLF \
  --past-months 6 \
  --bar-size "1 min" \
  --what TRADES \
  --port 4001
```

Run the first-5-minute direction strategy only when QQQ premarket is at least +/-0.5% in
the same direction:

```bash
uv run python -m stox.backtest \
  --symbols AAOI,LITE,COHR,CIEN,NBIS,SNDK,RGTI,IONQ,IREN,APLD,WOLF \
  --strategy first5qqq \
  --benchmark-symbol QQQ \
  --benchmark-threshold-pct 0.5 \
  --signal-minutes 5 \
  --exit-after-minutes 30 \
  --transaction-cost-bps 1
```

## Sentiment scaffold

Import a CSV with columns `ts`, `symbol`, `sentiment`:

```bash
uv run python -m stox.ingest.sentiment_import \
  --input data/sentiment.csv \
  --source demo \
  --ts-col ts \
  --symbol-col symbol \
  --score-col sentiment \
  --tz UTC
```

## Data layout

```
data/
  raw/
    bars/
      source=ib/
        date=2026-04-01/
          symbol=CRWV/
            part-*.parquet
  curated/
```

## Notes
- Use ISO timestamps with timezone (e.g., `2025-02-01T14:30:00Z`).
- Sentiment is handled as a separate dataset and joined at feature time.


uv run streamlit run streamlit_app.py
