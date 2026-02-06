from __future__ import annotations

import argparse
from pathlib import Path

from ..sentiment import load_sentiment_csv, write_sentiment


def main() -> None:
    parser = argparse.ArgumentParser(description="Import sentiment CSV into partitioned Parquet")
    parser.add_argument("--input", required=True, help="CSV file path")
    parser.add_argument("--source", required=True, help="Data source label, e.g. newsapi")
    parser.add_argument("--ts-col", default="ts")
    parser.add_argument("--symbol-col", default="symbol")
    parser.add_argument("--score-col", default="sentiment")
    parser.add_argument("--tz", default="UTC", help="Timezone for naive timestamps")

    args = parser.parse_args()

    df = load_sentiment_csv(
        Path(args.input).expanduser(),
        ts_col=args.ts_col,
        symbol_col=args.symbol_col,
        score_col=args.score_col,
        tz=args.tz,
    )

    path = write_sentiment(df, source=args.source)
    print(f"Wrote {df.height} sentiment rows to {path}")


if __name__ == "__main__":
    main()
