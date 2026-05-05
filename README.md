# stox2

Offline tick store + ML sandbox for US stocks. The focus is:
- ingesting tick data from IB
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

3) Fetch ticks (example):

```bash
uv run python -m stox.ingest.ib_fetch \
  --symbol AAPL \
  --exchange SMART \
  --currency USD \
  --start 2025-02-01T14:30:00Z \
  --end 2025-02-01T20:00:00Z \
  --what TRADES \
  --max 2000
```

Batch fetch for many symbols:

```bash
uv run python -m stox.ingest.ib_fetch_batch \
  --symbols AAPL,MSFT,NVDA \
  --start 2025-02-01T14:30:00Z \
  --end 2025-02-01T20:00:00Z \
  --what TRADES \
  --max 2000
```

4) Query with DuckDB (example):

```python
import duckdb
con = duckdb.connect()
con.sql("""
  SELECT symbol, date, COUNT(*) AS n
  FROM read_parquet('data/raw/ticks/source=ib/**/*.parquet')
  GROUP BY ALL
  ORDER BY date DESC
""").df()
```

5) Launch the local explorer:

```bash
uv run streamlit run streamlit_app.py
```

This opens a small local UI for browsing tick parquet data by symbol and date range.
The app exposes `Explorer` and `Settings` in the sidebar.

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
    ticks/
      source=ib/
        date=2025-02-01/
          symbol=AAPL/
            part-*.parquet
  curated/
```

## Notes
- Use ISO timestamps with timezone (e.g., `2025-02-01T14:30:00Z`).
- IB limits historical tick pulls; the ingest script pages sequentially.
- Sentiment is handled as a separate dataset and joined at feature time.
